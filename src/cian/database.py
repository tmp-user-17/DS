import sqlite3
import json
import pandas as pd

_loc_delim = ", "


def convert_raw_data(data: dict):
    objs = [
        {f"geo.coordinates.{i}": j for i, j in data["geo"]["coordinates"].items()},
        {f"building.{i}": j for i, j in data["building"].items()},
        {f"geo.undergrounds": data["geo"]["undergrounds"]},
    ]
    for i in objs:
        data.update(i)
    return data


class CianDatabase:
    def __init__(self):
        self._con = sqlite3.connect(":memory:")

    def open(self):
        self._con = sqlite3.connect("data/data.db", check_same_thread=False)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY,
                location_base TEXT,
                location TEXT,
                json JSON
            )
        """)
        self._con.execute("""
            CREATE INDEX IF NOT EXISTS offers_loc_base ON offers(location_base)
        """)
        self._con.execute("""
            CREATE INDEX IF NOT EXISTS offers_loc ON offers(location)
        """)

    def insert(self, offers):
        def _offer(data):
            index = data["id"]
            location_base = data["geo"]["address"][0]["title"]
            location = _loc_delim.join([i["title"] for i in data["geo"]["address"] if i["type"] == "location"])
            return index, location_base, location, json.dumps(data)

        cur = self._con.cursor()
        cur.executemany("""
            INSERT INTO offers (id, location_base, location, json) VALUES (?, ?, ?, JSON(?))
                ON CONFLICT(id) DO UPDATE SET
                    location_base = excluded.location_base,
                    location = excluded.location,
                    json = excluded.json
        """, [_offer(i) for i in offers])
        cur.close()
        self._con.commit()

    def location_base_stats(self):
        cur = self._con.cursor()
        cur.execute("""
            SELECT location_base, count(id) FROM offers
                GROUP BY location_base
        """)
        data = cur.fetchall()
        cur.close()

        loc_base, count = zip(*data)
        return pd.DataFrame({
            "Location": loc_base,
            "Offers count": count
        })

    def locations(self):
        cur = self._con.cursor()
        # Here "location" can be used instead "location_base" to allow user to select regions and villages
        cur.execute("""
            SELECT DISTINCT location_base FROM offers
        """)
        data = [i[0] for i in cur.fetchall()]
        cur.close()

        for i in data:
            parts = i.split(_loc_delim)
            if len(parts) > 1:
                data.append(_loc_delim.join(parts[:-1]))

        return sorted(list(set(data)))

    def select(self, location=None):
        cur = self._con.cursor()
        cur.execute("""
            SELECT json FROM offers
                WHERE location == ? OR location LIKE ?
        """, (location, f"{location},%"))
        data = [json.loads(i[0]) for i in cur.fetchall()]
        cur.close()

        return pd.DataFrame.from_records([convert_raw_data(i) for i in data])

    def close(self):
        self._con.close()
