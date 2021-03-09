import re
from functools import total_ordering




@total_ordering
class PrefixedNum:

    def __init__(self, val):
        val = str(val)
        if re.search(r"^([A-z]+[- ]?)?\d+$", val):
            match = re.search(r"^[A-z]+[- ]?", val)
            self.prefix = match.group() if match else ''
            self.number = int(re.search(r"\d+$", val).group())
        else:
            raise ValueError(f"Invalid prefixed number: {val}")


    def __bool__(self):
        return bool(self.number)


    def __hash__(self):
        return hash(str(self))


    def __str__(self):
        return f"{self.prefix}{self.number}"


    def __repr__(self):
        return str(self)


    def __add__(self, other):
        """Adds value to number"""
        if isinstance(other, int):
            return self.__class__(f"{self.prefix}{self.number + other}")

        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        if other.prefix and self.prefix != other.prefix:
            raise ValueError("Can't add two numbers with different prefixes")
        return self.number + other.number


    def __sub__(self, other):
        """Substracts value from number"""
        if isinstance(other, int):
            return self.__class__(f"{self.prefix}{self.number - other}")

        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        if other.prefix and self.prefix != other.prefix:
            raise ValueError("Can't subtract two numbers with different prefixes")
        return self.number - other.number


    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        return self.prefix == other.prefix and self.number == other.number


    def __lt__(self, other):
        if not isinstance(other, self.__class__):
            other = self.__class__(other)
        if self.prefix == other.prefix:
            return self.number < other.number
        return self.prefix < other.prefix
