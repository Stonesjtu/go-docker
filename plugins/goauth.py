from godocker.iAuthPlugin import IAuthPlugin
import logging

class goAuth(IAuthPlugin):
    def get_name(self):
        return "goauth"

    def get_type(self):
        return "Auth"
