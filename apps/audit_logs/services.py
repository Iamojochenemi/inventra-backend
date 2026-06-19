from django.contrib.contenttypes.models import ContentType
from django.core import serializers
import json
from .models import AuditLog, EntitySnapshot

def create_audit_log(user, obj, action, old_values=None, new_values=None, 
                     ip_address=None, user_agent=None, reason=""):
    """
    Create an audit log entry for an entity change.
    
    Args:
        user: User who made the change
        obj: The model instance that was changed
        action: 'create', 'update', 'delete', or 'restore'
        old_values: Dict of previous field values
        new_values: Dict of new field values
        ip_address: IP address of the request
        user_agent: User agent string
        reason: Reason for the change
    """
    content_type = ContentType.objects.get_for_model(obj)
    
    audit_log = AuditLog.objects.create(
        user=user,
        content_type=content_type,
        object_id=obj.pk,
        action=action,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
        reason=reason
    )
    
    return audit_log

def create_entity_snapshot(obj, reason=""):
    """
    Create a snapshot of an entity's current state.
    
    Args:
        obj: The model instance to snapshot
        reason: Why the snapshot was taken
    """
    content_type = ContentType.objects.get_for_model(obj)
    
    # Serialize the object to JSON
    serialized = serializers.serialize('json', [obj])
    snapshot_data = json.loads(serialized)[0]['fields']
    
    snapshot = EntitySnapshot.objects.create(
        content_type=content_type,
        object_id=obj.pk,
        snapshot_data=snapshot_data,
        reason=reason
    )
    
    return snapshot

def get_entity_history(obj):
    """
    Get all audit logs for an entity.
    
    Args:
        obj: The model instance
        
    Returns:
        QuerySet of AuditLog entries
    """
    content_type = ContentType.objects.get_for_model(obj)
    return AuditLog.objects.filter(
        content_type=content_type,
        object_id=obj.pk
    ).order_by('-created_at')

def get_entity_snapshots(obj):
    """
    Get all snapshots for an entity.
    
    Args:
        obj: The model instance
        
    Returns:
        QuerySet of EntitySnapshot entries
    """
    content_type = ContentType.objects.get_for_model(obj)
    return EntitySnapshot.objects.filter(
        content_type=content_type,
        object_id=obj.pk
    ).order_by('-created_at')

def get_changed_fields(old_values, new_values):
    """
    Compare old and new values and return only the changed fields.
    
    Args:
        old_values: Dict of previous values
        new_values: Dict of new values
        
    Returns:
        Dict of {field_name: (old_value, new_value)} for changed fields
    """
    if not old_values or not new_values:
        return {}
    
    changed = {}
    all_keys = set(old_values.keys()) | set(new_values.keys())
    
    for key in all_keys:
        old_val = old_values.get(key)
        new_val = new_values.get(key)
        
        if old_val != new_val:
            changed[key] = (old_val, new_val)
    
    return changed