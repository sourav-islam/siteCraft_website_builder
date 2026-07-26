import redis
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# Initialize Redis client
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True  # Automatically decode bytes to strings
)


def _serialize_locker(locker):
    """Convert a User instance to a lightweight dict suitable for JSON responses."""
    if locker is None:
        return None
    return {
        "id": locker.id,
        "username": locker.username,
        "email": locker.email,
    }


class LockService:
    """Service for managing resource locks with TTL using Redis."""

    @staticmethod
    def get_lock_key(resource_type, resource_id):
        """Generate a unique lock key for a resource."""
        return f"lock:{resource_type}:{resource_id}"

    @classmethod
    def acquire_lock(cls, resource_type, resource_id, user_id, ttl=None):
        """
        Try to acquire a lock for a resource.
        
        Args:
            resource_type: Type of resource (e.g., 'site', 'page')
            resource_id: ID of the resource
            user_id: ID of the user trying to acquire the lock
            ttl: Time to live in seconds (defaults to settings.LOCK_TTL)
        
        Returns:
            dict: Status with 'success' flag and 'locker' info if already locked
        """
        if ttl is None:
            ttl = settings.LOCK_TTL

        lock_key = cls.get_lock_key(resource_type, resource_id)

        # Try to set the lock only if it doesn't exist (NX = "only if not exists")
        lock_acquired = redis_client.set(
            name=lock_key,
            value=str(user_id),
            ex=ttl,  # Expire after ttl seconds
            nx=True  # Only set if key doesn't exist
        )

        if lock_acquired:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                user = None
            return {
                "success": True,
                "lock_key": lock_key,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "locked": True,
                "locker": _serialize_locker(user),
                "ttl_seconds": ttl,
                "ttl_remaining": ttl,
                "acquired_at": timezone.now().isoformat(),
            }

        # Lock already exists, get locker info
        locker_id = redis_client.get(lock_key)
        locker = None
        if locker_id:
            try:
                locker = User.objects.get(id=locker_id)
            except User.DoesNotExist:
                pass

        ttl_remaining = redis_client.ttl(lock_key)

        return {
            "success": False,
            "lock_key": lock_key,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "locked": True,
            "locker": _serialize_locker(locker),
            "ttl_remaining": ttl_remaining,
        }

    @classmethod
    def release_lock(cls, resource_type, resource_id, user_id):
        """
        Release a lock for a resource (only by the user who holds it).
        
        Args:
            resource_type: Type of resource (e.g., 'site', 'page')
            resource_id: ID of the resource
            user_id: ID of the user trying to release the lock
        
        Returns:
            dict: Rich result with success flag, reason, lock info, and locker
        """
        lock_key = cls.get_lock_key(resource_type, resource_id)
        current_locker_id = redis_client.get(lock_key)

        # No lock exists at all
        if not current_locker_id:
            return {
                "success": False,
                "reason": "no_lock",
                "message": "No active lock exists for this resource.",
                "lock_key": lock_key,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "locked": False,
                "locker": None,
            }

        # Another user holds the lock
        if current_locker_id != str(user_id):
            try:
                locker = User.objects.get(id=current_locker_id)
            except User.DoesNotExist:
                locker = None
            ttl_remaining = redis_client.ttl(lock_key)
            return {
                "success": False,
                "reason": "not_owner",
                "message": "You cannot release this lock — it is held by another user.",
                "lock_key": lock_key,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "locked": True,
                "locker": _serialize_locker(locker),
                "ttl_remaining": ttl_remaining,
            }

        # Requesting user holds the lock — release it
        redis_client.delete(lock_key)
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            user = None
        return {
            "success": True,
            "reason": "released",
            "message": "Lock released successfully.",
            "lock_key": lock_key,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "locked": False,
            "locker": None,
            "released_by": _serialize_locker(user),
            "released_at": timezone.now().isoformat(),
        }

    @classmethod
    def get_lock_status(cls, resource_type, resource_id):
        """
        Get the current status of a lock.
        
        Args:
            resource_type: Type of resource (e.g., 'site', 'page')
            resource_id: ID of the resource
        
        Returns:
            dict: Rich lock status info
        """
        lock_key = cls.get_lock_key(resource_type, resource_id)
        locker_id = redis_client.get(lock_key)

        if not locker_id:
            return {
                "lock_key": lock_key,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "locked": False,
                "locker": None,
                "ttl_remaining": None,
            }

        locker = None
        try:
            locker = User.objects.get(id=locker_id)
        except User.DoesNotExist:
            pass

        ttl_remaining = redis_client.ttl(lock_key)

        return {
            "lock_key": lock_key,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "locked": True,
            "locker": _serialize_locker(locker),
            "ttl_remaining": ttl_remaining,
            "ttl_seconds": settings.LOCK_TTL,
        }
    

    @classmethod
    def heartbeat(cls, resource_type, resource_id, user_id):
        """
        Refresh the TTL of an existing lock.

        Returns:
            dict: Rich result with success flag, message, and full lock info
        """

        lock_key = cls.get_lock_key(resource_type, resource_id)
        current_locker_id = redis_client.get(lock_key)
        ttl = settings.LOCK_TTL

        # No lock exists
        if not current_locker_id:
            return {
                "success": False,
                "reason": "no_lock",
                "message": "No active lock exists for this resource — acquire a lock first.",
                "lock_key": lock_key,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "locked": False,
                "locker": None,
            }

        # Another user holds the lock
        if current_locker_id != str(user_id):
            try:
                locker = User.objects.get(id=current_locker_id)
            except User.DoesNotExist:
                locker = None
            ttl_remaining = redis_client.ttl(lock_key)
            return {
                "success": False,
                "reason": "not_owner",
                "message": "You cannot refresh this lock — it is held by another user.",
                "lock_key": lock_key,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "locked": True,
                "locker": _serialize_locker(locker),
                "ttl_remaining": ttl_remaining,
            }

        # Requesting user holds the lock — refresh TTL
        redis_client.expire(lock_key, ttl)
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            user = None
        return {
            "success": True,
            "reason": "refreshed",
            "message": "Heartbeat received — lock TTL refreshed successfully.",
            "lock_key": lock_key,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "locked": True,
            "locker": _serialize_locker(user),
            "ttl_seconds": ttl,
            "ttl_remaining": ttl,
            "refreshed_at": timezone.now().isoformat(),
        }