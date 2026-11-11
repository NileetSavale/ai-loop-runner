# Case 41

## The issue

[Bug]: ConciseDateFormatter not showing year anywhere when plotting <12 months
### Bug summary

When I plot < 1 year and January is not included in the x-axis, the year doesn't show up anywhere.
This bug is different from bug #21670 (fixed in #21785).

### Code for reproduction

```python
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

#create time array
initial = datetime(2021,2,14,0,0,0)
time_array = [initial + timedelta(days=x) for x in range(1,200)]

#create data array
data = [-x**2/20000 for x in range(1,200)]


#plot data
fig,ax = plt.subplots()
ax.plot(time_array,data) 
        
locator = mdates.AutoDateLocator()
formatter = mdates.ConciseDateFormatter(locator)

ax.grid(True)
ax.set_ylabel("Temperature ($\degree$C)")
ax.xaxis.set_major_locator(locator)   
ax.xaxis.set_major_formatter(formatter)
fig.autofmt_xdate() #automatically makes the x-labels rotate
```


### Actual outcome

![image](https://user-images.githubusercontent.com/15143365/154090257-c7813f1c-f9ea-4252-86bf-f84e449c2f46.png)


### Expected outcome

I expect the year "2021" to show in the offset, to the right of the x-axis

### Additional information

I'm using Spyder IDE, v5.1.5

### Operating system

Windows 10

### Matplotlib Version

3.4.3

### Matplotlib Backend

Qt5Agg

### Python version

3.9.1

### Jupyter version

_No response_

### Installation

conda

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/lib/matplotlib/dates.py b/lib/matplotlib/dates.py
index 4d8ddf3ee5..834de189c0 100755
--- a/lib/matplotlib/dates.py
+++ b/lib/matplotlib/dates.py
@@ -797,7 +797,7 @@ class ConciseDateFormatter(ticker.Formatter):
         # 3: hours, 4: minutes, 5: seconds, 6: microseconds
         for level in range(5, -1, -1):
             if len(np.unique(tickdate[:, level])) > 1:
-                if level < 2:
+                if level == 0:
                     show_offset = False
                 break
             elif level == 0:
diff --git a/lib/matplotlib/tests/test_dates.py b/lib/matplotlib/tests/test_dates.py
index a78c39c560..e6389faf45 100755
--- a/lib/matplotlib/tests/test_dates.py
+++ b/lib/matplotlib/tests/test_dates.py
@@ -595,7 +595,7 @@ def test_concise_formatter():
     (datetime.timedelta(hours=1), '1997-Jan-01'),
     (datetime.timedelta(days=1), '1997-Jan-02'),
     (datetime.timedelta(weeks=1), '1997-Jan'),
-    (datetime.timedelta(weeks=26), ''),
+    (datetime.timedelta(weeks=26), '1997'),
     (datetime.timedelta(weeks=520), '')
 ])
 def test_concise_formatter_show_offset(t_delta, expected):
```

## The official fix

```diff
diff --git a/lib/matplotlib/dates.py b/lib/matplotlib/dates.py
--- a/lib/matplotlib/dates.py
+++ b/lib/matplotlib/dates.py
@@ -796,8 +796,10 @@ def format_ticks(self, values):
         # mostly 0: years,  1: months,  2: days,
         # 3: hours, 4: minutes, 5: seconds, 6: microseconds
         for level in range(5, -1, -1):
-            if len(np.unique(tickdate[:, level])) > 1:
-                if level < 2:
+            unique = np.unique(tickdate[:, level])
+            if len(unique) > 1:
+                # if 1 is included in unique, the year is shown in ticks
+                if level < 2 and np.any(unique == 1):
                     show_offset = False
                 break
             elif level == 0:
```

## The official tests added or changed for this issue

```diff
diff --git a/lib/matplotlib/tests/test_dates.py b/lib/matplotlib/tests/test_dates.py
--- a/lib/matplotlib/tests/test_dates.py
+++ b/lib/matplotlib/tests/test_dates.py
@@ -630,6 +630,10 @@ def test_offset_changes():
     ax.set_xlim(d1, d1 + datetime.timedelta(weeks=3))
     fig.draw_without_rendering()
     assert formatter.get_offset() == '1997-Jan'
+    ax.set_xlim(d1 + datetime.timedelta(weeks=7),
+                d1 + datetime.timedelta(weeks=30))
+    fig.draw_without_rendering()
+    assert formatter.get_offset() == '1997'
     ax.set_xlim(d1, d1 + datetime.timedelta(weeks=520))
     fig.draw_without_rendering()
     assert formatter.get_offset() == ''
```

## Hidden tests the cheap fix failed

- `lib/matplotlib/tests/test_dates.py::test_concise_formatter_show_offset[t_delta5-]`

## Test output for those tests (excerpt)

```
________________ test_concise_formatter_show_offset[t_delta5-] _________________

t_delta = datetime.timedelta(days=182), expected = ''

    @pytest.mark.parametrize('t_delta, expected', [
        (datetime.timedelta(seconds=0.01), '1997-Jan-01 00:00'),
        (datetime.timedelta(minutes=1), '1997-Jan-01 00:01'),
        (datetime.timedelta(hours=1), '1997-Jan-01'),
        (datetime.timedelta(days=1), '1997-Jan-02'),
        (datetime.timedelta(weeks=1), '1997-Jan'),
        (datetime.timedelta(weeks=26), ''),
        (datetime.timedelta(weeks=520), '')
    ])
    def test_concise_formatter_show_offset(t_delta, expected):
        d1 = datetime.datetime(1997, 1, 1)
        d2 = d1 + t_delta
    
        fig, ax = plt.subplots()
        locator = mdates.AutoDateLocator()
        formatter = mdates.ConciseDateFormatter(locator)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
    
        ax.plot([d1, d2], [0, 0])
        fig.canvas.draw()
>       assert formatter.get_offset() == expected
E       AssertionError: assert '1997' == ''
E         
E         + 1997

lib/matplotlib/tests/test_dates.py:613: AssertionError
==================================== PASSES ====================================
___________________________ test_too_many_date_ticks ___________________________
------------------------------ Captured log call -------------------------------
WARNING  matplotlib.ticker:ticker.py:1646 Locator attempting to generate 1461 ticks ([10246.0, ..., 11706.0]), which exceeds Locator.MAXTICKS (1000).
=========================== short test summary info ============================
PASSED lib/matplotlib/tests/test_dates.py::test_date_numpyx
PASSED lib/matplotlib/tests/test_dates.py::test_date_date2num_numpy[datetime64[s]-t00]
PASSED lib/matplotlib/tests/test_dates.py::test_date_date2num_numpy[datetime64[s]-t01]
PASSED lib/matplotlib/tests/test_dates.py::test_date_date2num_numpy[datetime64[s]-t02]
FAILED lib/matplotlib/tests/test_dates.py::test_concise_formatter_show_offset[t_delta5-]
```
