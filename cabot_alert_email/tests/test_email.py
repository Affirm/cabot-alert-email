from cabot.plugin_test_utils import PluginTestCase
from mock import Mock, patch, call

from cabot.cabotapp.models import Service
from cabot_alert_email import models

# these are globals so we can pass them into the @patch decorator
fake_mail_class = Mock()
fake_message = Mock()
fake_send_mail = Mock()
fake_attach_alternative = Mock()
fake_attach = Mock()


class TestEmailAlerts(PluginTestCase):
    def setUp(self):
        super(TestEmailAlerts, self).setUp()

        # add the email alert to the test service
        self.email_alert = models.EmailAlert.objects.get(title=models.EmailAlert.name)
        self.service.alerts.add(self.email_alert)
        self.service.save()

        # set up mocks
        fake_mail_class.return_value = fake_message
        fake_message.configure_mock(send=fake_send_mail, attach_alternative=fake_attach_alternative, attach=fake_attach)

        # reset mock call counts (since they're globals the don't get recreated with each test...)
        for mock in fake_mail_class, fake_message, fake_send_mail, fake_attach_alternative, fake_attach:
            mock.reset_mock()

    def test_model_attributes(self):
        self.assertEqual(self.service.users_to_notify.all().count(), 1)
        self.assertEqual(self.service.users_to_notify.get(pk=self.user.pk).username, self.user.username)
        self.assertEqual(self.service.alerts.all().count(), 1)

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_error_to_passing(self):
        self.transition_service_status(Service.ERROR_STATUS, Service.PASSING_STATUS)

        # check the plaintext version
        fake_mail_class.assert_called_with('Service back to normal: Service',
                                           u'Service Service http://localhost/service/2194/ is back to normal.\n\n',
                                           'Cabot <cabot@example.com>',
                                           [self.user.email, self.duty_officer.email])
        # check the HTML version
        fake_attach_alternative.assert_has_calls([
            call(u'\n<table>\n  <tr>\n    <td colspan=3>\n'
                 u'Service <a href="http://localhost/service/2194/"><b>Service</b></a> is back to normal.\n'
                 u'    </td>\n  </tr>\n\n  <tr><td>\n\n',
                 'text/html')
        ])
        # no images should have been attached
        self.assertFalse(fake_attach.called)
        # make sure it was actually sent, not just constructed
        self.assertTrue(fake_send_mail.called)

    @patch('cabot_alert_email.models.EmailMultiAlternatives', fake_mail_class)
    def test_passing_to_error(self):
        self.run_checks([(self.http_check, False, False), (self.es_check, False, False)], Service.PASSING_STATUS)

        # check the plaintext version of the email
        fake_mail_class.assert_called_with('CRITICAL status for service: Service',
                                           u'Service Service http://localhost/service/2194/ alerting with status: '
                                           u'CRITICAL.\n\n'
                                           u'CHECKS FAILING:\n'
                                           u'  FAILING - ES Metric Check - Type: Elasticsearch check - Importance: Error\n'
                                           u'  FAILING - Http Check - Type: HTTP check - Importance: Critical\n\n'
                                           u'Passing checks:\n'
                                           u'  PASSING - Jenkins Check - Type: Jenkins check - Importance: Error\n'
                                           u'  PASSING - TCP Check - Type: TCP check - Importance: Error\n\n\n',
                                           'Cabot <cabot@example.com>',
                                           [self.user.email, self.duty_officer.email])

        # check that we attached the image to the email
        fake_attach.assert_has_calls([
            call('ES Metric Check.png', self.es_check.get_status_image(), 'image/png')
        ])

        # check the html version of the email (what people usually see...)
        fake_attach_alternative.assert_has_calls([
            call(u'''
<table>
  <tr>
    <td colspan=3>
Service <a href="http://localhost/service/2194/"><b>Service</b></a> alerting with status: CRITICAL.
    </td>
  </tr>

  <tr><td>

<b>Failing Checks</b><br/>
  <table cellpadding='4' cellspacing='1' border='1' align='left'>
    <tr>
      <th bgcolor='dedede'>Check Name</th>
      <th bgcolor='dedede'>Check Type</th>
      <th bgcolor='dedede'>Importance</th>
    </tr>
  
    <tr>
      <td><a href='http://localhost/check/10104/'>ES Metric Check</a></td>
      <td>Elasticsearch check</td>
      <td>Error</td>
    </tr>
  
    <tr>
      <td><a href='http://localhost/check/10102/'>Http Check</a></td>
      <td>HTTP check</td>
      <td>Critical</td>
    </tr>
  
  </table>
  </td></tr>
  <tr></tr>
  <tr><td>

  
<b>Passing Checks</b><br/>
  <table cellpadding='4' cellspacing='1' border='1' align='left'>
    <tr>
      <th bgcolor='dedede'>Check Name</th>
      <th bgcolor='dedede'>Check Type</th>
      <th bgcolor='dedede'>Importance</th>
    </tr>
    
    <tr>
      <td><a href='http://localhost/check/10101/'>Jenkins Check</a></td>
      <td>Jenkins check</td>
      <td>Error</td>
    </tr>
    
    <tr>
      <td><a href='http://localhost/check/10103/'>TCP Check</a></td>
      <td>TCP check</td>
      <td>Error</td>
    </tr>
    
  </table>
  </td></tr></table>
  

''',
                 'text/html')
        ])

        # make sure it was actually sent
        self.assertTrue(fake_send_mail.called)
