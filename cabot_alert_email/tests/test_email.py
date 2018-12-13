from django.contrib.auth.models import User
from django.utils import timezone

from cabot.cabotapp.tests.utils import LocalTestCase
from mock import Mock, patch

from cabot.cabotapp.models import UserProfile, Service, StatusCheckResult
from cabot_alert_email import models
from cabot.cabotapp.alert import update_alert_plugins, send_alert

fake_mail_class = Mock()
fake_message = Mock()
fake_send_mail = Mock()
fake_attach_alternative = Mock()


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

        fake_mail_class.return_value = fake_message
        fake_message.configure_mock(send=fake_send_mail, attach_alternative=fake_attach_alternative)
        for mock in (fake_mail_class, fake_message, fake_send_mail, fake_attach_alternative):
            mock.reset_mock()

    def test_model_attributes(self):
        self.assertEqual(self.service.users_to_notify.all().count(), 1)
        self.assertEqual(self.service.users_to_notify.get(pk=self.user.pk).username, self.user.username)

        self.assertEqual(self.service.alerts.all().count(), 1)

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_send_mail(self):
        self.service.overall_status = Service.PASSING_STATUS
        self.service.old_overall_status = Service.ERROR_STATUS
        self.service.save()
        self.service.alert()
        fake_mail_class.assert_called_with('Service back to normal: Service', u'Service Service http://localhost/service/2194/ is back to normal.\n\n', 'Cabot <cabot@example.com>', [u'test@userprofile.co.uk'])
        fake_send_mail.assert_called_with()

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_failure_alert(self):
        # Most recent failed
        self.service.overall_status = Service.ERROR_STATUS
        self.service.old_overall_status = Service.PASSING_STATUS
        self.service.save()

        self.service.alert()
        fake_mail_class.assert_called_with('ERROR status for service: Service',
                                           u'Service Service http://localhost/service/2194/ alerting with status: '
                                           u'ERROR.\n\n'
                                           u'CHECKS FAILING:\n\n'
                                           u'Passing checks:\n'
                                           u'  PASSING - Http Check - Type: HTTP check - Importance: Critical\n'
                                           u'  PASSING - Jenkins Check - Type: Jenkins check - Importance: Error\n'
                                           u'  PASSING - TCP Check - Type: TCP check - Importance: Error\n\n\n',
                                           'Cabot <cabot@example.com>', [u'test@userprofile.co.uk'])
        fake_send_mail.assert_called_with()

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_email_duty_officers(self):
        self.service.old_overall_status = Service.PASSING_STATUS
        self.service.overall_status = Service.ERROR_STATUS
        self.service.save()

        duty_officer = User.objects.create_user('test', email='test@test.test')

        send_alert(self.service, [duty_officer], [])
        fake_mail_class.assert_called_with('ERROR status for service: Service',
                                           u'Service Service http://localhost/service/2194/ alerting with status: '
                                           u'ERROR.\n\n'
                                           u'CHECKS FAILING:\n\n'
                                           u'Passing checks:\n'
                                           u'  PASSING - Http Check - Type: HTTP check - Importance: Critical\n'
                                           u'  PASSING - Jenkins Check - Type: Jenkins check - Importance: Error\n'
                                           u'  PASSING - TCP Check - Type: TCP check - Importance: Error\n\n\n',
                                           'Cabot <cabot@example.com>',
                                           [u'test@userprofile.co.uk', u'test@test.test'])
        fake_send_mail.assert_called_with()

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_error_to_acked(self):
        self.service.overall_status = Service.ACKED_STATUS
        self.service.old_overall_status = Service.ERROR_STATUS
        self.service.save()

        self.service.alert()
        self.assertFalse(fake_send_mail.called)

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_acked_to_error(self):
        self.service.overall_status = Service.ERROR_STATUS
        self.service.old_overall_status = Service.ACKED_STATUS
        self.service.save()

        self.service.alert()
        self.assertTrue(fake_send_mail.called)

    def _add_result(self, check, succeeded, acked=False):
        now = timezone.now() - timezone.timedelta(seconds=1)
        result = StatusCheckResult(check=check, succeeded=succeeded, acked=acked,
                                   time=now, time_complete=now + timezone.timedelta(seconds=1))
        result.succeeded = succeeded
        result.acked = acked
        result.save()
        check.last_run = now
        check.save()
        return result

    # test formatting
    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_partially_acked_service(self):
        self.service.overall_status = Service.ERROR_STATUS
        self.service.old_overall_status = self.service.overall_status
        self.service.save()

        self._add_result(self.http_check, succeeded=False, acked=True)
        self._add_result(self.jenkins_check, succeeded=False, acked=False)

        self.service.alert()
        fake_mail_class.assert_called_with('ERROR status for service: Service',
                                           u'Service Service http://localhost/service/2194/ alerting with status: '
                                           u'ERROR.\n\n'
                                           u'CHECKS FAILING:\n'
                                           u'  FAILING - Http Check (acked) - Type: HTTP check - Importance: Critical\n'
                                           u'  FAILING - Jenkins Check - Type: Jenkins check - Importance: Error\n\n'
                                           u'Passing checks:\n'
                                           u'  PASSING - TCP Check - Type: TCP check - Importance: Error\n\n\n',
                                           'Cabot <cabot@example.com>', [u'test@userprofile.co.uk'])
