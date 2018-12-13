from cabot.plugin_test_utils import PluginTestCase
from mock import Mock, patch

from cabot.cabotapp.models import Service
from cabot_alert_email import models

# these are globals so we can pass them into the @patch decorator
fake_mail_class = Mock()
fake_message = Mock()
fake_send_mail = Mock()
fake_attach_alternative = Mock()


class TestEmailAlerts(PluginTestCase):
    def setUp(self):
        super(TestEmailAlerts, self).setUp()

        # add the email alert to the test service
        self.email_alert = models.EmailAlert.objects.get(title=models.EmailAlert.name)
        self.service.alerts.add(self.email_alert)
        self.service.save()

        # set up mocks
        fake_mail_class.return_value = fake_message
        fake_message.configure_mock(send=fake_send_mail, attach_alternative=fake_attach_alternative)

        # reset mock call counts (since they're globals the don't get recreated with each test...)
        for mock in (fake_mail_class, fake_message, fake_send_mail, fake_attach_alternative):
            mock.reset_mock()

    def test_model_attributes(self):
        self.assertEqual(self.service.users_to_notify.all().count(), 1)
        self.assertEqual(self.service.users_to_notify.get(pk=self.user.pk).username, self.user.username)
        self.assertEqual(self.service.alerts.all().count(), 1)

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_error_to_passing(self):
        self.transition_service(Service.ERROR_STATUS, Service.PASSING_STATUS)
        fake_mail_class.assert_called_with('Service back to normal: Service',
                                           u'Service Service http://localhost/service/2194/ is back to normal.\n\n',
                                           'Cabot <cabot@example.com>',
                                           [self.user.email, self.duty_officer.email])
        # TODO test HTML alternative
        self.assertTrue(fake_send_mail.called)

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_passing_to_error(self):
        self.run_checks([(self.http_check, False, False)], Service.PASSING_STATUS)

        fake_mail_class.assert_called_with('CRITICAL status for service: Service',
                                           u'Service Service http://localhost/service/2194/ alerting with status: '
                                           u'CRITICAL.\n\n'
                                           u'CHECKS FAILING:\n'
                                           u'  FAILING - Http Check - Type: HTTP check - Importance: Critical\n\n'
                                           u'Passing checks:\n'
                                           u'  PASSING - Jenkins Check - Type: Jenkins check - Importance: Error\n'
                                           u'  PASSING - TCP Check - Type: TCP check - Importance: Error\n\n\n',
                                           'Cabot <cabot@example.com>',
                                           [self.user.email, self.duty_officer.email])
        # TODO test HTML alternative
        self.assertTrue(fake_send_mail.called)

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_error_to_acked(self):
        self.transition_service(Service.PASSING_STATUS, Service.ACKED_STATUS)
        self.assertFalse(fake_send_mail.called)

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_acked_to_error(self):
        self.transition_service(Service.ACKED_STATUS, Service.ERROR_STATUS)
        self.assertTrue(fake_send_mail.called)

    # test formatting
    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_partially_acked_service(self):
        self.run_checks([(self.http_check, False, True), (self.jenkins_check, False, False)], Service.ERROR_STATUS)

        fake_mail_class.assert_called_with('ERROR status for service: Service',
                                           u'Service Service http://localhost/service/2194/ alerting with status: '
                                           u'ERROR.\n\n'
                                           u'CHECKS FAILING:\n'
                                           u'  FAILING - Http Check (acked) - Type: HTTP check - Importance: Critical\n'
                                           u'  FAILING - Jenkins Check - Type: Jenkins check - Importance: Error\n\n'
                                           u'Passing checks:\n'
                                           u'  PASSING - TCP Check - Type: TCP check - Importance: Error\n\n\n',
                                           'Cabot <cabot@example.com>',
                                           [self.user.email, self.duty_officer.email])
        # TODO test HTML alternative
        self.assertTrue(fake_send_mail.called)
