"""
Middleware to add cache control headers to API responses
"""


class NoCacheMiddleware:
    """
    Middleware to add cache-control headers to prevent browser caching of API responses.
    This ensures that when data is deleted (like tournaments), the frontend immediately
    reflects the changes without requiring a hard refresh.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only add no-cache headers to API endpoints
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"

        return response
