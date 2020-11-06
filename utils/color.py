
class Color:

    def __init__(self, red, green, blue):
        self.reset = 0
        self.red = red
        self.green = green
        self.blue = blue

    def __mod__(self, msg):
        """
        Return the msg with color as foreground
        """
        rgb = f"{self.red};{self.green};{self.blue}"
        msg_colored = f"\x1b[38;2;{rgb}m{msg}\x1b[{self.reset}m"
        return msg_colored

    def mod(self, msg):
        return self.__mod__(msg)


white = Color(255, 255, 255)
blue = Color(51, 153, 255)
green = Color(0, 204, 0)
yellow = Color(255, 255, 51)
orange = Color(255, 128, 0)
red = Color(255, 51, 51)
grey = Color(192, 192, 192)
grey_dark_25 = Color(64, 64, 64)
grey_dark_30 = Color(77, 77, 77)
grey_dark_40 = Color(102, 102, 102)
grey_dark_50 = Color(128, 128, 128)
grey_blue = Color(0, 76, 153)
