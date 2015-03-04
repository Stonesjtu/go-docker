from godocker.iAuthPlugin import IAuthPlugin
import logging

class GoAuth(IAuthPlugin):
    def get_name(self):
        return "goauth"

    def get_type(self):
        return "Auth"
