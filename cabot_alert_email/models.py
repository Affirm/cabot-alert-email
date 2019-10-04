from os import environ as env

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template

from cabot.cabotapp.alert import AlertPlugin

email_txt_template = """Service {{ service.name }} {{ scheme }}://{{ host }}{% url 'service' pk=service.id %} {% if service.overall_status != service.PASSING_STATUS %}alerting with status: {{ service.overall_status }}{% else %}is back to normal{% endif %}.
{% if service.overall_status != service.PASSING_STATUS %}
CHECKS FAILING:{% for check in service.all_failing_checks %}
  FAILING - {{ check.name }}{% if check.calculated_status == 'acked' %} (acked){% endif %} - Type: {{ check.check_category }} - Importance: {{ check.get_importance_display }}{% endfor %}
{% endif %}
"""

email_html_template = """
<html>
  <head>
     <title>Cabot Alert</title>

<style type=3D"text/css">a {
  color: #0099cc;
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

table {
  border: 1px solid #c0c0c0;
  border-collapse: collapse;
  border-spacing: 0;
  color: #333;
  font: 11px "Helvetica Neue", Helvetica Arial, "Lucida Grande", sans-serif=
;
  width: 100%;
}

th {
  background: #dedede;
  border: 1px solid #c0c0c0;
  font-weight: 700;
  padding: 4px 4px;
  text-align: left;
}

th.pivot {
  background: #e6e6e6;
  text-align: center;
}

th.dimension, .dimension a, .pivot a {
  color: #0099cc;
}

th.measure, .measure a {
  color: #f26100;
}

td {
  border: none;
  line-height: 18px;
  padding: 1px 3px;
}

tr:nth-child(even) td {
  background-color: #e6e6e6;
}

tr:nth-child(even) td + td {
  border-left: 1px solid #fff;
}

.index, .right {
  text-align: right;
}

.dimension + .measure, .dimension + .pivot {
  border-left: 2px solid #000;
}

.single_value {
  font-size: 2em;
}</style>
</head><body><p></p><p>
<table>
  <tr>
    <td colspan=3>
Service <a href="{{ scheme }}://{{ host }}{% url 'service' pk=service.id %}"><b>{{ service.name }}</b></a> {% if service.overall_status != service.PASSING_STATUS %}alerting with status: {{ service.overall_status }}{% else %}is back to normal{% endif %}.
    </td>
  </tr>

  <tr><td>
{% if service.overall_status != service.PASSING_STATUS %}
<b>Failing Checks</b><br/>
  <table border=3D'1' cellspacing=3D'=
0' cellpadding=3D'3' style=3D'border: 1px solid #c0c0c0; border-collapse: c=
ollapse;'>
   <thead>
    <tr>
      <th class=3D'dimension'>Check Name</th>
      <th class=3D'dimension'>Check Type</th>
      <th class=3D'dimension'>Importance</th>
      <th class=3D'dimension'>Error</th>
    </tr>
   </thead>
   <tbody>
  {% for check in service.all_failing_checks %}
    <tr>
      <td class=3D'dimension'><a href='{{ scheme }}://{{ host }}{% url 'check' pk=check.id %}'>{{ check.name }}</a>{% if check.calculated_status == 'acked' %} (acked){% endif %}</td>
      <td class=3D'dimension'>{{ check.check_category }}</td>
      <td class=3D'dimension'>{{ check.get_importance_display }}</td>
      <td class=3D'dimension'>{{ '\n'.join(check.last_result.tags) | default:'' | safe }}</td>
    </tr>
  {% endfor %}
   </tbody>
  </table>
  </td></tr>
 </tbody>
</table></body></html>
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

        # don't send emails for acked services
        if service.overall_status == service.ACKED_STATUS:
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
