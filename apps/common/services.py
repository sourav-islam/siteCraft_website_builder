import redis
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

# Initialize Redis client
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True  # Automatically decode bytes to strings
)


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
            return {"success": True}

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
            "locker": locker,
            "ttl_remaining": ttl_remaining
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
            bool: Whether the lock was successfully released
        """
        lock_key = cls.get_lock_key(resource_type, resource_id)
        current_locker_id = redis_client.get(lock_key)

        if current_locker_id and current_locker_id == str(user_id):
            redis_client.delete(lock_key)
            return True

        return False

    @classmethod
    def get_lock_status(cls, resource_type, resource_id):
        """
        Get the current status of a lock.
        
        Args:
            resource_type: Type of resource (e.g., 'site', 'page')
            resource_id: ID of the resource
        
        Returns:
            dict: Lock status info
        """
        lock_key = cls.get_lock_key(resource_type, resource_id)
        locker_id = redis_client.get(lock_key)

        if not locker_id:
            return {"locked": False}

        locker = None
        try:
            locker = User.objects.get(id=locker_id)
        except User.DoesNotExist:
            pass

        ttl_remaining = redis_client.ttl(lock_key)

        return {
            "locked": True,
            "locker": locker,
            "ttl_remaining": ttl_remaining
        }
