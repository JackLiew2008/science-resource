import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email():
    try:
        # 邮箱账号和密码
        sender_email = "liuzj_jack@163.com"
        sender_password = "liuzj2008"
        receiver_email = "liuzj_jkack@hotmail.com"

        # 创建邮件内容
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = receiver_email
        message["Subject"] = "Test Email"

        body = "This is a test email from Flask."
        message.attach(MIMEText(body, "plain"))

        # 连接到阿里云 SMTP 服务器
        server = smtplib.SMTP_TLS("smtpdm.aliyun.com", 587)  # 或使用 587 端口
        server.login(sender_email, sender_password)

        # 发送邮件
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
        print("邮件已发送!")

    except smtplib.SMTPAuthenticationError as e:
        print("邮件发送失败:", e)
    except Exception as e:
        print("其他错误:", e)

# 调用函数发送邮件
send_email()

# import smtplib
# import logging
#
# logging.basicConfig(level=logging.DEBUG)
#
#
# def send_email():
#     try:
#         sender_email = "liuzj_jack@163.com"
#         sender_password = "liuzj2008"
#         receiver_email = "jackliew950@gmail.com"
#
#         message = "Test email from Flask"
#
#         # 连接到阿里云 SMTP 服务器
#         server = smtplib.SMTP_SSL("smtpdm.aliyun.com", 465)
#         server.set_debuglevel(1)  # 启用调试模式
#         server.login(sender_email, sender_password)
#
#         # 发送邮件
#         server.sendmail(sender_email, receiver_email, message)
#         server.quit()
#         print("邮件已发送!")
#     except Exception as e:
#         print("错误信息:", e)
#
#
# send_email()