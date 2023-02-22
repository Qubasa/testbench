import logging

class CustomFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    green = "\u001b[32m"
    blue = "\u001b[34m"
    reset = "\x1b[0m"

    def format(color):
        return f"%(asctime)s - %(name)s - {color} %(levelname)s {reset} - %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: format(blue),
        logging.INFO: format(green),
        logging.WARNING: format(yellow),
        logging.ERROR: format(red),
        logging.CRITICAL: format(bold_red)
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)