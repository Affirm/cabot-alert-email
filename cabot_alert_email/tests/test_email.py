from django.contrib.auth.models import User

from cabot.cabotapp.tests.tests_basic import LocalTestCase
from mock import Mock, patch
from requests.models import Response

from cabot.cabotapp.models import UserProfile, Service
from cabot.metricsapp.models import ElasticsearchStatusCheck, GrafanaPanel, GrafanaInstance, ElasticsearchSource
from cabot_alert_email import models
from cabot.cabotapp.alert import update_alert_plugins


class TestEmailAlerts(LocalTestCase):
    def setUp(self):
        super(TestEmailAlerts, self).setUp()

        self.user_profile = UserProfile(user=self.user)
        self.user_profile.save()
        self.user_profile.user.email = "test@userprofile.co.uk"
        self.user_profile.user.save()
        self.service.users_to_notify.add(self.user)
        self.service.save()

        update_alert_plugins()
        self.email_alert = models.EmailAlert.objects.get(title=models.EmailAlert.name)
        self.email_alert.save()

        self.service.alerts.add(self.email_alert)
        self.service.save()
        self.service.update_status()

    def test_model_attributes(self):
        self.assertEqual(self.service.users_to_notify.all().count(), 1)
        self.assertEqual(self.service.users_to_notify.get(email='test@userprofile.co.uk').username, self.user.username)

        self.assertEqual(self.service.alerts.all().count(), 1)

    @patch('cabot_alert_email.models.EmailMessage')
    def test_send_mail(self, fake_send_mail):
        self.service.overall_status = Service.PASSING_STATUS
        self.service.old_overall_status = Service.ERROR_STATUS
        self.service.save()
        self.service.alert()
        fake_send_mail.assert_called_with(body=u'Service Service http://localhost/service/{}/'
                                               u' is back to normal.\n\n'.format(self.service.id),
                                          subject='Service back to normal: Service',
                                          to=[u'test@userprofile.co.uk'],
                                          from_email='Cabot <cabot@example.com>')

    @patch('cabot_alert_email.models.EmailMessage')
    def test_failure_alert(self, fake_send_mail):
        # Most recent failed
        self.service.overall_status = Service.CALCULATED_FAILING_STATUS
        self.service.old_overall_status = Service.PASSING_STATUS
        self.service.save()
        self.service.alert()
        fake_send_mail.assert_called_with(body=u'Service Service http://localhost/service/{}/ alerting with status: '
                                               u'failing.\n\nCHECKS FAILING:\n\n\nPassing checks:\n  '
                                               u'PASSING - Graphite Check - Type: Metric check - Importance: Error\n  '
                                               u'PASSING - Http Check - Type: HTTP check - Importance: Critical\n  '
                                               u'PASSING - Jenkins Check - Type: Jenkins check '
                                               u'- Importance: Error\n\n\n'.format(self.service.id),
                                          subject='failing status for service: Service',
                                          to=[u'test@userprofile.co.uk'],
                                          from_email='Cabot <cabot@example.com>')

    @patch('cabot_alert_email.models.EmailMessage')
    def test_email_duty_officers(self, fake_send_mail):
        self.service.overall_status = Service.CALCULATED_FAILING_STATUS
        self.service.old_overall_status = Service.PASSING_STATUS
        self.service.save()

        duty_officer = User.objects.create_user('test')
        duty_officer.email = 'test@test.test'
        duty_officer.save()

        self.email_alert.send_alert(self.service, [self.user], [duty_officer])
        fake_send_mail.assert_called_with(body=u'Service Service http://localhost/service/{}/ alerting with status: '
                                               u'failing.\n\nCHECKS FAILING:\n\n\nPassing checks:\n  PASSING - '
                                               u'Graphite Check - Type: Metric check - Importance: Error\n  PASSING '
                                               u'- Http Check - Type: HTTP check - Importance: Critical\n  PASSING '
                                               u'- Jenkins Check - Type: Jenkins check - Importance: Error\n\n\n'
                                               .format(self.service.id),
                                          subject='failing status for service: Service',
                                          to=[u'test@userprofile.co.uk', u'test@test.test'],
                                          from_email='Cabot <cabot@example.com>')

    @patch('cabot_alert_email.models.EmailMessage')
    @patch('cabot_alert_email.models.EmailMessage.attach')
    @patch('cabot.metricsapp.models.grafana.GrafanaInstance.get_request')
    def test_grafana_attachment(self, fake_request, fake_attach, fake_send_mail):
        fake_request.return_value = Response()
        fake_request.return_value.status_code = 200
        fake_request.return_value._content = '12345'

        instance = GrafanaInstance.objects.create(
            name='test',
            url='https://reallygreaturl.yep',
            api_key='271828'
        )
        panel = GrafanaPanel.objects.create(
            grafana_instance=instance,
            dashboard_uri='db/hi-im-panel',
            panel_id=1000000,
            series_ids='abc',
            selected_series='a',
            panel_url='https://reallygreaturl.yep/dashboard-solo/db/hi-im-panel&var-params=$__all'
        )
        source = ElasticsearchSource.objects.create(name='hi', urls='')
        check = ElasticsearchStatusCheck.objects.create(
            name='checkycheck',
            created_by=self.user,
            source=source,
            check_type='>=',
            warning_value=3.5,
            high_alert_importance='CRITICAL',
            high_alert_value=3.0,
            queries='[{"aggs": {"agg": {"terms": {"field": "a1"},'
                    '"aggs": {"agg": {"terms": {"field": "b2"},'
                    '"aggs": {"agg": {"date_histogram": {"field": "@timestamp","interval": "hour"},'
                    '"aggs": {"max": {"max": {"field": "timing"}}}}}}}}}}]',
            time_range=10000,
            active=True,
            grafana_panel=panel
        )

        check.calculated_status = Service.CALCULATED_FAILING_STATUS
        self.service.status_checks.add(check)
        self.service.save()

        self.service.old_overall_status = Service.PASSING_STATUS
        self.service.overall_status = Service.CALCULATED_FAILING_STATUS
        self.service.save()

        self.assertEqual(self.service.old_overall_status, Service.PASSING_STATUS)
        self.assertEqual(self.service.overall_status, Service.CALCULATED_FAILING_STATUS)

        self.service.alert()
        fake_send_mail.assert_called_with(
            body=u'Service Service http://localhost/service/3/ alerting with status: failing.\n\n'
                 u'CHECKS FAILING:\n'
                 u'Grafana links for the failing checks:\n'
                 u'https://reallygreaturl.yep/dashboard-solo/db/hi-im-panel&amp;var-params=$__all.\n\n'
                 u'Passing checks:\n  PASSING - checkycheck - Type:  - Importance: Error\n  '
                 u'PASSING - Graphite Check - Type: Metric check - Importance: Error\n  '
                 u'PASSING - Http Check - Type: HTTP check - Importance: Critical\n  '
                 u'PASSING - Jenkins Check - Type: Jenkins check - Importance: Error\n\n\n'
                .format(self.service.id),
            subject='failing status for service: Service', to=[u'test@userprofile.co.uk'],
            from_email='Cabot <cabot@example.com>')

        fake_request.assert_called_with('render/dashboard-solo/db/hi-im-panel&var-params=All')
        fake_attach.assert_called_with('checkycheck.png', '12345', 'image/png')
