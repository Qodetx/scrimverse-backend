"""
Utility functions for payment processing
"""
from datetime import date, datetime, time
from decimal import Decimal


def serialize_for_json(data):
    """
    Convert Django model data to JSON-serializable format
    Handles Decimal, datetime, date, time, and file fields
    """
    serialized = {}
    for key, value in data.items():
        if hasattr(value, "name"):  # File field
            serialized[key] = value.name
        elif hasattr(value, "id"):  # Foreign key
            serialized[key] = value.id
        elif isinstance(value, Decimal):
            serialized[key] = float(value)
        elif isinstance(value, (datetime, date)):
            serialized[key] = value.isoformat()
        elif isinstance(value, time):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def deserialize_tournament_data(data):
    """
    Convert JSON data back to Django model-compatible format for Tournament
    """
    converted = data.copy()

    # Convert datetime strings back to datetime objects
    datetime_fields = ["registration_start", "registration_end", "tournament_start", "tournament_end"]
    for field in datetime_fields:
        if field in converted and isinstance(converted[field], str):
            converted[field] = datetime.fromisoformat(converted[field])

    # Convert date strings
    if "tournament_date" in converted and isinstance(converted["tournament_date"], str):
        converted["tournament_date"] = datetime.fromisoformat(converted["tournament_date"]).date()

    # Convert time strings
    if "tournament_time" in converted and isinstance(converted["tournament_time"], str):
        hour, minute, second = converted["tournament_time"].split(":")
        converted["tournament_time"] = time(int(hour), int(minute), int(float(second)))

    # Convert numeric fields back to Decimal
    decimal_fields = ["entry_fee", "prize_pool", "plan_price"]
    for field in decimal_fields:
        if field in converted and not isinstance(converted[field], Decimal):
            converted[field] = Decimal(str(converted[field]))

    return converted
