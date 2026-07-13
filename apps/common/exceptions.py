from rest_framework.exceptions import APIException


class ResourceNotFound(APIException):
    status_code = 404
    default_detail = "Resource not found."
    default_code = "resource_not_found"


class BadRequest(APIException):
    status_code = 400
    default_detail = "Bad request."
    default_code = "bad_request"