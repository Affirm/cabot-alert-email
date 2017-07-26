from os import environ as env

from django.conf import settings
from django.template import Context, Template
from django.core.mail import EmailMultiAlternatives

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
Service <a href="{{ scheme }}://{{ host }}{% url 'service' pk=service.id %}"><b>{{ service.name }}</b></a> {% if service.overall_status != service.PASSING_STATUS %}alerting with status: {{ service.overall_status }}{% else %}is back to normal{% endif %}.

{% if service.overall_status != service.PASSING_STATUS %}
<b><u>Failing Checks</u><b><br/>
  <table>
    <tr>
      <th>Service Name</th>
      <th>Check Type</th>
      <th>Importance</th>
    </tr>
  {% for check in service.all_failing_checks %}
    <tr>
      <td><b>{{ check.name }}</b></td>
      <td>{{ check.check_category }}</td>
      <td>{{ check.get_importance_display }}</td>
    </tr>
  {% endfor %}
  </table>
  {% if service.all_passing_checks %}
<br/>
<b><u>Passing Checks</u><b><br/>
  <table>
    <tr>
      <th>Service Name</th>
      <th>Check Type</th>
      <th>Importance</th>
    </tr>
    {% for check in service.all_passing_checks %}
    <tr>
      <td><b>{{ check.name }}</b></td>
      <td>{{ check.check_category }}</td>
      <td>{{ check.get_importance_display }}</td>
    </tr>
    {% endfor %}
  {% endif %}
{% endif %}
"""


class EmailAlert(AlertPlugin):
    name = "Email"
    author = "Jonathan Balls"

    def send_alert(self, service, users, duty_officers):
        emails = [u.email for u in users if u.email] + \
                 [u.email for u in duty_officers if u.email]
        if not emails:
            return
        c = Context({
            'service': service,
            'host': settings.WWW_HTTP_HOST,
            'scheme': settings.WWW_SCHEME
        })
        if service.overall_status != service.PASSING_STATUS:
            subject = '%s status for service: %s' % (
                service.overall_status, service.name)
        else:
            subject = 'Service back to normal: %s' % (service.name,)

        text_message = Template(email_txt_template).render(c)
        html_message = Template(email_html_template).render(c)
        sender = 'Cabot <%s>' % env.get('CABOT_FROM_EMAIL')

        msg = EmailMultiAlternatives(subject, text_message, sender, emails)
        msg.attach_alternative(html_message, 'text/html')
        msg.mixed_subtype = 'related'

        # Insert images here

        msg.send()
