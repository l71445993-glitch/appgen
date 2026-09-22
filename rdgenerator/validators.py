from django.core.exceptions import ValidationError


def minimum_password_help_text(min_length):
    return f"密码至少 {min_length} 位，允许使用字母、数字或符号。"


class MinimumLengthValidator:
    def __init__(self, min_length=6):
        self.min_length = min_length

    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(
                "密码至少需要 %(min_length)d 个字符。",
                code="password_too_short",
                params={"min_length": self.min_length},
            )

    def get_help_text(self):
        return minimum_password_help_text(self.min_length)
