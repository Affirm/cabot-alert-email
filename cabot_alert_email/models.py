import time
from os import environ as env
from pyvirtualdisplay import Display
from selenium import webdriver

from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from django.template import Context, Template

from cabot.cabotapp.alert import AlertPlugin


email_template = """Service {{ service.name }} {{ scheme }}://{{ host }}{% url 'service' pk=service.id %} {% if service.overall_status != service.PASSING_STATUS %}alerting with status: {{ service.overall_status }}{% else %}is back to normal{% endif %}.
{% if service.overall_status != service.PASSING_STATUS %}
CHECKS FAILING:{% for check in service.all_failing_checks %}
  FAILING - {{ check.name }} - Type: {{ check.check_category }} - Importance: {{ check.get_importance_display }}{% endfor %}
{% if service.all_passing_checks %}
Passing checks:{% for check in service.all_passing_checks %}
  PASSING - {{ check.name }} - Type: {{ check.check_category }} - Importance: {{ check.get_importance_display }}{% endfor %}
{% endif %}
{% endif %}
"""

class EmailAlert(AlertPlugin):
    name = "Email"
    author = "Jonathan Balls"

    def send_alert(self, service, users, duty_officers, url=None):
        emails = [u.email for u in users if u.email] + [u.email for u in duty_officers if u.email]
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

        t = Template(email_template)
        email = EmailMessage(
            subject,
            t.render(c),
            'Cabot <{}>'.format(env.get('CABOT_FROM_EMAIL')),
            emails
        )
        if url is not None:
            screenshot_file = self._get_graph_screenshot(url, service.name)
            email.attach_file(screenshot_file)

        email.send()

    # apt-get install xvfb firefox
    # pip install selenium pyvirtualdisplay
    # install geckodriver (or chromedriver or something)
    def _get_graph_screenshot(self, url, name):
        display = Display(visible=0, size=(800, 600))
        display.start()
        browser = webdriver.Firefox()
        browser.get(url)
        file = '{}-{}.png'.format(str(time.now()), name)
        browser.save_screenshot(file)
        browser.quit()
        # display.stop() ? or something
        return './{}'.format(file)
