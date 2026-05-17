try:
    import time as _time
    def sleep(seconds):
        _time.sleep(seconds)
    
    def sleep_ms(ms):
        _time.sleep(ms / 1000.0)
        
    def ticks_ms():
        return int(_time.time() * 1000)
        
    def localtime(secs=None):
        t = _time.localtime(secs)
        # MicroPython order: (year, month, mday, hour, minute, second, weekday, yearday)
        return (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, t.tm_wday, t.tm_yday)
        
    def ticks_diff(ticks1, ticks2):
        return ticks1 - ticks2
        
    def time():
        return int(_time.time())
except ImportError:
    pass
