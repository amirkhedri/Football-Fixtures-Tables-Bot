import jdatetime
import datetime

def to_persian_digits(text: str) -> str:
    en_to_fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return str(text).translate(en_to_fa)

def get_jalali_date_string(date_iso: str = None) -> str:
    if date_iso:
        dt = datetime.datetime.fromisoformat(date_iso).date()
        jdate = jdatetime.date.fromgregorian(date=dt)
    else:
        jdate = jdatetime.date.today()
        
    months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", 
              "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    
    raw_date = f"{jdate.day} {months[jdate.month - 1]} {jdate.year}"
    return to_persian_digits(raw_date)