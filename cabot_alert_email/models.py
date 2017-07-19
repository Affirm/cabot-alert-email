from os import environ as env

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template

from cabot.cabotapp.alert import AlertPlugin

email_txt_template = """Service {{ service.name }} {{ scheme }}://{{ host }}{% url 'service' pk=service.id %} {% if service.overall_status != service.PASSING_STATUS %}alerting with status: {{ service.overall_status }}{% else %}is back to normal{% endif %}.
{% if service.overall_status != service.PASSING_STATUS %}
CHECKS FAILING:{% for check in service.all_failing_checks %}
  FAILING - {{ check.name }} - Type: {{ check.check_category }} - Importance: {{ check.get_importance_display }}{% endfor %}
{% if service.all_passing_checks %}
Passing checks:{% for check in service.all_passing_checks %}
  PASSING - {{ check.name }} - Type: {{ check.check_category }} - Importance: {{ check.get_importance_display }}{% endfor %}
{% endif %}
{% endif %}
"""

email_html_template = """
<table>
  <tr>
    <td colspan=3>
Service <a href="{{ scheme }}://{{ host }}{% url 'service' pk=service.id %}"><b>{{ service.name }}</b></a> {% if service.overall_status != service.PASSING_STATUS %}alerting with status: {{ service.overall_status }}{% else %}is back to normal{% endif %}.
    </td>
  </tr>

  <tr><td>
{% if service.overall_status != service.PASSING_STATUS %}
<b>Failing Checks</b><br/>
  <table cellpadding='4' cellspacing='1' border='1' align='left'>
    <tr>
      <th bgcolor='dedede'>Check Name</th>
      <th bgcolor='dedede'>Check Type</th>
      <th bgcolor='dedede'>Importance</th>
    </tr>
  {% for check in service.all_failing_checks %}
    <tr>
      <td><a href='{{ scheme }}://{{ host }}{% url 'check' pk=check.id %}'>{{ check.name }}</a></td>
      <td>{{ check.check_category }}</td>
      <td>{{ check.get_importance_display }}</td>
    </tr>
  {% endfor %}
  </table>
  </td></tr>
  <tr></tr>
  <tr><td>

  {% if service.all_passing_checks %}
<b>Passing Checks</b><br/>
  <table cellpadding='4' cellspacing='1' border='1' align='left'>
    <tr>
      <th bgcolor='dedede'>Check Name</th>
      <th bgcolor='dedede'>Check Type</th>
      <th bgcolor='dedede'>Importance</th>
    </tr>
    {% for check in service.all_passing_checks %}
    <tr>
      <td><a href='{{ scheme }}://{{ host }}{% url 'check' pk=check.id %}'>{{ check.name }}</a></td>
      <td>{{ check.check_category }}</td>
      <td>{{ check.get_importance_display }}</td>
    </tr>
    {% endfor %}
  </table>
  </td></tr></table>
  {% endif %}
{% endif %}
"""


class EmailAlert(AlertPlugin):
    name = "Email"
    author = "Jonathan Balls"

    def send_alert(self, service, users, duty_officers):
        """
        Send an email to the specified users with the service status and (possibly) Grafana panel images/links.
        """
        emails = [u.email for u in users if u.email] + \
                 [u.email for u in duty_officers if u.email]

        if not emails:
            return

        c = Context({
            'service': service,
            'host': settings.WWW_HTTP_HOST,
            'scheme': settings.WWW_SCHEME
        })

        images = {}
        if service.overall_status != service.PASSING_STATUS:
            subject = '%s status for service: %s' % (
                service.overall_status, service.name)

            failing_metrics_checks = service.all_failing_checks()

            # Get the panel urls and name: image mapping for the failing metrics checks
            for check in failing_metrics_checks:
                image = check.get_status_image()
                if image is not None:
                    images[check.name] = image

        else:
            subject = 'Service back to normal: %s' % (service.name,)

        text_message = Template(email_txt_template).render(c)
        html_message = Template(email_html_template).render(c)
        sender = 'Cabot <%s>' % env.get('CABOT_FROM_EMAIL')

        msg = EmailMultiAlternatives(subject, text_message, sender, emails)
        msg.attach_alternative(html_message, 'text/html')
        msg.mixed_subtype = 'related'

        # Insert images here
        for name, image in images.iteritems():
            msg.attach('{}.png'.format(name), image, 'image/png')

        msg.send()
