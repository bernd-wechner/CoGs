'''
Python and web widget datetimes accept broader time offsets than postgres it seems. Sowe want to be able to force conformance into a database safe range.
'''

from dateutil import parser
from datetime import timezone, timedelta

def clean_submitted_datetime(raw_dt_string):
    try:
        dt = parser.isoparse(raw_dt_string)
        
        if dt.tzinfo:
            offset_hours = dt.utcoffset().total_seconds() / 3600
            
            # If the offset is outside the DB-safe range (+/- 15)
            if abs(offset_hours) > 15:
                # 1. Convert to UTC to get the absolute "moment"
                utc_dt = dt.astimezone(timezone.utc)
                
                # 2. Calculate the "wrapped" offset (e.g., 23:50 -> -00:10)
                # Mathematically: ((offset + 12) % 24) - 12
                wrapped_offset_hours = ((offset_hours + 12) % 24) - 12
                
                # 3. Project that moment back into the normalized offset
                new_tz = timezone(timedelta(hours=wrapped_offset_hours))
                dt = utc_dt.astimezone(new_tz)
                
                return dt.isoformat()
                
        return raw_dt_string
    except (ValueError, TypeError):
        # Let Django's standard field validation handle malformed strings
        return raw_dt_string
    
source = "2025-11-09T00:20:00+23:50"
print(source, parser.isoparse(source).astimezone(timezone.utc))
clean = clean_submitted_datetime(source)
print(clean, parser.isoparse(clean).astimezone(timezone.utc))