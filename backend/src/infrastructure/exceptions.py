class InvalidFileExtensionError(Exception):
    """
    Вызывается, если расширение или MIME-тип загружаемого файла не поддерживаются.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class FileTooLargeError(Exception):
    """
    Вызывается, когда размер загружаемого файла превышает установленный лимит.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class MediaSaveError(Exception):
    """
    Вызывается, если произошла ошибка при сохранении медиафайла на диск.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
