class UserNotFoundError(Exception):
    def __init__(self, message: str = "User not found"):
        self.message = message
        super().__init__(self.message)

class InvalidPhoneNumber(Exception):
    def __init__(self, message: str = "Phone number isn`t valid. Example format: +71234567890"):
        self.message = message
        super().__init__(self.message)

class OTPCodeAlreadySent(Exception):
    def __init__(self, ttl: int):
        self.message = "Code already sent. Try again later. "
        if ttl:
            self.message += "Please wait {}s before requesting a new one.".format(
                ttl,
            )
        self.ttl = ttl
        super().__init__(self.message)

class FullnameValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)