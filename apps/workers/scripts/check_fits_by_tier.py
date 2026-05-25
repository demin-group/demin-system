from shared.db import get_session
from sqlalchemy import text
with get_session('prod') as s:
    r = s.execute(text('''
        SELECT
          tier,
          count(*) FILTER (WHERE ia_fit='fit')        AS fits,
          count(*) FILTER (WHERE ia_fit='no_fit')     AS no_fits,
          count(*) FILTER (WHERE ia_fit='dudoso')     AS dudosos,
          count(*)                                    AS total
        FROM companies
        WHERE tier IN ('T1','T2','T3','T4')
        GROUP BY tier
        ORDER BY tier;
    ''')).all()
    for row in r:
        print(f'{row.tier}: fits={row.fits}  no_fits={row.no_fits}  dudosos={row.dudosos}  total={row.total}')
