from tournaments.models import Tournament, Match
from django.utils import timezone
import datetime as _dt

TID = 12

def run():
    try:
        t = Tournament.objects.get(id=TID)
    except Tournament.DoesNotExist:
        print('Tournament not found')
        return

    m = Match.objects.filter(group__tournament=t, scheduled_date__isnull=False).order_by('scheduled_date','scheduled_time').first()
    if not m:
        print('No scheduled matches found for tournament', TID)
        return

    mdate = m.scheduled_date
    mtime = m.scheduled_time or _dt.time.min
    dt = _dt.datetime.combine(mdate, mtime)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    t.tournament_start = dt
    t.tournament_date = mdate
    t.tournament_time = mtime
    t.save()
    print('Updated tournament', TID, 'tournament_start ->', t.tournament_start)

if __name__ == '__main__':
    run()
