import smtplib
from email.mime.text import MIMEText
import logging


class Notify:
    '''
    Manage notifications related to jobs
    '''

    config = None
    logger = None

    def __init__(self):
        pass

    @staticmethod
    def set_config(config):
        Notify.config = config

    @staticmethod
    def set_logger(logger):
        Notify.logger = logger

    @staticmethod
    def notify_email(task, opt_msg=None):
        '''
        Sends an email to *to*.
        '''
        if 'email_smtp_host' not in Notify.config or Notify.config.email_smtp_host is None:
            return

        if 'email' not in task['user'] or task['user']['email'] is None:
            return

        if 'notify' not in task or not task['notify']['email']:
            return

        to = task['user']['email']
        subject = 'Task '+str(task['id'])+': '+str(task['status']['primary'])
        message = opt_msg
        if opt_msg is None:
            message = 'Task '+str(task['id'])+ '('+str(task['meta']['name'])+') switched to status '+str(task['status']['primary'])+'/'+str(task['status']['secondary'])
        # Create a text/plain message
        msg = MIMEText(message)

        msg['Subject'] = subject
        msg['From'] = Notify.config.email_from
        msg['To'] = to

        # Send the message via our own SMTP server, but don't include the
        # envelope header.
        try:
            s = smtplib.SMTP(Notify.config.email_smtp_host, Notify.config.email_smtp_port)
            if Notify.config.email_smtp_tls:
                s.starttls()
            if Notify.config.email_smtp_user:
                s.login(Notify.config.email_smtp_user, Notify.config.email_smtp_password)
            s.sendmail(msg['From'], [msg['To']], msg.as_string())
            s.quit()
        except Exception as e:
            self.logger.error('Email error: '+str(e))
