class Permission:
    # Organization
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    ORG_DELETE = "org:delete"

    # Users
    USER_INVITE = "user:invite"
    USER_READ = "user:read"
    USER_UPDATE_ROLE = "user:update_role"
    USER_REMOVE = "user:remove"

    # Projects
    PROJECT_CREATE = "project:create"
    PROJECT_READ = "project:read"
    PROJECT_UPDATE = "project:update"
    PROJECT_DELETE = "project:delete"

    # Queues
    QUEUE_CREATE = "queue:create"
    QUEUE_READ = "queue:read"
    QUEUE_UPDATE = "queue:update"
    QUEUE_DELETE = "queue:delete"
    QUEUE_PAUSE = "queue:pause"
    QUEUE_CONFIGURE = "queue:configure"  # rate limits, shards

    # Jobs
    JOB_CREATE = "job:create"
    JOB_READ = "job:read"
    JOB_CANCEL = "job:cancel"
    JOB_RETRY = "job:retry"
    JOB_VIEW_LOGS = "job:view_logs"

    # Workers
    WORKER_READ = "worker:read"
    WORKER_FORCE_OFFLINE = "worker:force_offline"

    # DLQ
    DLQ_READ = "dlq:read"
    DLQ_REPLAY = "dlq:replay"
    DLQ_RESOLVE = "dlq:resolve"

    # Workflows
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_READ = "workflow:read"

    @classmethod
    def all(cls) -> set[str]:
        return {
            v
            for k, v in vars(cls).items()
            if not k.startswith("_") and isinstance(v, str)
        }


ALL_PERMISSIONS: set[str] = Permission.all()

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": set(ALL_PERMISSIONS),
    # Everything except deleting the org and promoting/demoting other users'
    # roles (that stays owner-only, so an admin can never engineer their own
    # or anyone else's escalation to owner).
    "admin": ALL_PERMISSIONS - {Permission.ORG_DELETE, Permission.USER_UPDATE_ROLE},
    "member": {
        Permission.ORG_READ,
        Permission.USER_READ,
        Permission.PROJECT_READ,
        Permission.PROJECT_CREATE,
        Permission.QUEUE_READ,
        Permission.QUEUE_CREATE,
        Permission.QUEUE_PAUSE,
        Permission.JOB_CREATE,
        Permission.JOB_READ,
        Permission.JOB_CANCEL,
        Permission.JOB_RETRY,
        Permission.JOB_VIEW_LOGS,
        Permission.WORKER_READ,
        Permission.DLQ_READ,
        Permission.DLQ_REPLAY,
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_READ,
    },
    "viewer": {
        Permission.ORG_READ,
        Permission.USER_READ,
        Permission.PROJECT_READ,
        Permission.QUEUE_READ,
        Permission.JOB_READ,
        Permission.JOB_VIEW_LOGS,
        Permission.WORKER_READ,
        Permission.DLQ_READ,
        Permission.WORKFLOW_READ,
    },
}


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def get_permissions_for_role(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, set()))


def roles_with_permission(permission: str) -> list[str]:
    return sorted(
        role for role, perms in ROLE_PERMISSIONS.items() if permission in perms
    )
