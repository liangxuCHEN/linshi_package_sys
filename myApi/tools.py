# encoding=utf8
import smtplib
from email.mime.text import MIMEText
import my_settings


"""
    mail_to = 'lchen@europely.com,reservation@europely.com'
    # mail_to = 'lchen@europely.com'
    res = send_mail(mail_to, u"明天出行订单提醒", body)
"""


def send_mail(mail_to, subject, msg_txt):
    # Record the MIME types of both parts - text/plain and text/html.
    msg = MIMEText(msg_txt, 'html', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = my_settings.MAIL_FROM
    msg['To'] = mail_to
    server = smtplib.SMTP(my_settings.SMTP_SERVER, 25)
    try:
        server.login(my_settings.MAIL_FROM, my_settings.PW)
        mailto_list = mail_to.strip().split(",")
        if len(mailto_list) > 1:
            for mailtoi in mailto_list:
                server.sendmail(my_settings.MAIL_FROM, mailtoi.strip(), msg.as_string())
        else:
            server.sendmail(my_settings.MAIL_FROM, mail_to, msg.as_string())
    except:
        server.quit()
        return False

    server.quit()
    return True

