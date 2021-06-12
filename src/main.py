
import streamlit as st
import pydeck as pdk
from math import ceil
from shapely.geometry.point import Point
from shapely.geometry.multipoint import MultiPoint
from transliterate import translit
from cian import *
import pandas as pd
import geopandas as gp
import streamlit as st
import networkx as nx

page = st.sidebar.selectbox("Page", ["Analyzing", "Scrapping"])

st.markdown("Source code and description is available on [https://github.com/tmp-user-17/DS](GitHub)")
st.text("")

if page == "Scrapping":
    with st.echo(code_location="below"):
        @st.cache(allow_output_mutation=True, show_spinner=False)
        def db():
            cdb = CianDatabase()
            cdb.open()
            return cdb

        def scrap(scrapper, link, stat, use_proxy=False):
            cian = scrapper(link, use_proxy=use_proxy)
            stat.text("Preparing Cian scrapper")
            try:
                cian.prepare()
                cian.scrap(lambda pages, count: stat.text(f"Already scrapped {count} offers from {pages} pages"))
            finally:
                cian.cleanup()
            stat.text(f"Scrapping finished with {len(cian.results)} offers")

        st.header("Scrap Cian offers")
        link = st.text_input("Search list url", "https://www.cian.ru/kupit-kvartiru-1-komn-ili-2-komn/")
        btn1, btn2, btn3 = st.beta_columns(3)
        stat = st.empty()

        if btn1.button("Scrap using proxied rest api"):
            scrap(CianRest, link, stat, use_proxy=True)
        if btn2.button("Scrap using rest api"):
            scrap(CianRest, link, stat)
        if btn3.button("Scrap using browser"):
            scrap(CianBrowser, link, stat)
        
        st.markdown("""
            To properly try out scrapping it is recommended to run project locally to avoid spamming from server and getting captcha

            Rest api scrapping will result in ip ban and captcha request. Proxies are randomly selected from internet and unfortunattely already banned

            Please do not stop scrapping and dont try to run it many times. Streamlit has no feature to make graceful shutdown
        """)

        st.table(db().location_base_stats())


if page == "Analyzing":
    st.header("Analyze Cian offers")

    with st.echo(code_location="below"):
        @st.cache(allow_output_mutation=True, show_spinner=False)
        def db():
            cdb = CianDatabase()
            cdb.open()
            return cdb


        @st.cache(allow_output_mutation=True)
        def select(location):
            return db().select(location)
            
        result = st.empty()
        echo = st.empty()

        location = st.selectbox("Location", db().locations())
        data = select(location)
        st.success(f"Selected {len(data)} offers (clear cache after scrapping)")

    with st.echo(code_location="below"):
        def parseColor(color):
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            if len(color) == 8:
                a = int(color[6:8], 16)
                return [r, g, b, a]
            return [r, g, b]
            
        @st.cache(allow_output_mutation=True, show_spinner=False)
        def extract_undergrounds(data):
            data_under = gp.GeoDataFrame(crs="EPSG:4326", data=[{
                "offerId": i["id"],
                "time": j["time"],
                "stationId": j["id"],
                "stationName": j["name"],
                "lineId": j["lineId"],
                "lineColor": parseColor(j["lineColor"]),
                "geometry": Point(i["geo.coordinates.lng"], i["geo.coordinates.lat"])
            } for _, i in data.iterrows() for j in i["geo.undergrounds"]])
            return data_under.dropna()

        data_under = extract_undergrounds(data)

        st.markdown("Apartment colored in colors of underground stations that are walking-reachable in realtor's info")
        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/light-v9',
            initial_view_state=pdk.ViewState(
                latitude=data["geo.coordinates.lat"].mean(),
                longitude=data["geo.coordinates.lng"].mean(),
                zoom=9,
            ),
            layers=[
                pdk.Layer(
                    "ScatterplotLayer",
                    data=data_under,
                    get_position="geometry.coordinates",
                    get_fill_color="lineColor",
                    opacity=0.1,
                    get_radius=200,
                ),
            ],
        ))

    with st.echo(code_location="below"):
        @st.cache(allow_output_mutation=True)
        def find_stations(data_under, time_lim):
            stations = []
            for i in data_under["stationId"].unique():
                station = data_under[data_under["stationId"] == i].iloc[0]
                points = data_under[(data_under["stationId"] == i) & (data_under["time"] <= time_lim)].geometry
                if len(points) > 0:
                    stations.append({
                        "lineId": station["lineId"],
                        "lineColor": station["lineColor"],
                        "name": translit(station["stationName"], reversed=True),
                        "geometry": MultiPoint(points.values),
                    })

            stations = gp.GeoDataFrame.from_records(stations)

            stations.geometry = stations.geometry.convex_hull

            centers = stations.copy()
            centers.geometry = centers.geometry.centroid

            return stations, centers

        @st.cache(allow_output_mutation=True)
        def find_lines(centers):
            lines = {}
            for _, i in centers.iterrows():
                if i["lineId"] not in lines:
                    lines[i["lineId"]] = {
                        "lineId": i["lineId"],
                        "lineColor": i["lineColor"],
                        "stations": []
                    }
                lines[i["lineId"]]["stations"].append(i.geometry)
            
            sections = []
            for line in lines.values():
                g = nx.Graph()
                for i in range(len(line["stations"])):
                    for j in range(i):
                        x1, y1 = line["stations"][i].x, line["stations"][i].y
                        x2, y2 = line["stations"][j].x, line["stations"][j].y
                        g.add_edge(i, j, weight=((x2 - x1)**2 + (y2 - y1)**2)**0.5)

                g = nx.minimum_spanning_tree(g)
                for i in g.edges:
                    sections.append({
                        "name": f"Line #{line['lineId']}",
                        "color": line["lineColor"],
                        "path": [
                            [line["stations"][i[0]].x, line["stations"][i[0]].y],
                            [line["stations"][i[1]].x, line["stations"][i[1]].y],
                        ]
                    })
            
            return pd.DataFrame.from_records(sections)

        time_max = int(ceil(data_under["time"].max()))
        time_lim = st.select_slider("[Apartment sampling] max walking time from object to underground station", list(range(1, time_max + 1)), min(20, time_max))

        stations, centers = find_stations(data_under, time_lim)
        lines = find_lines(centers)

        st.markdown("""
        Here are approximated positions of uderground stations areas that was selected based on max walk time

        Also here are approximated train paths that are computed using graph minimum spanning tree algorithm.
        It is not an exact solution but it is enough to show overall situation
        """)

        show_names, show_areas, show_lines = st.beta_columns(3)
        show_names = show_names.checkbox("Show station names", False)
        show_areas = show_areas.checkbox("Show data areas", True)
        show_lines = show_lines.checkbox("Show underground lines", True)

        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/light-v9',
            initial_view_state=pdk.ViewState(
                latitude=data["geo.coordinates.lat"].mean(),
                longitude=data["geo.coordinates.lng"].mean(),
                zoom=9,
            ),
            layers=[
                *([pdk.Layer(
                    "GeoJsonLayer",
                    data=stations,
                    get_fill_color="lineColor",
                    opacity=0.01,
                    get_radius=200,
                )] if show_areas else []),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=centers,
                    get_position="geometry.coordinates",
                    get_fill_color="lineColor",
                    opacity=1,
                    get_radius=200,
                ),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=data_under,
                    get_position="geometry.coordinates",
                    get_radius=50,
                    get_fill_color="[0, 0, 0]",
                    opacity=0.25,
                ),
                *([pdk.Layer(
                    "PathLayer",
                    data=lines,
                    get_path="path",
                    get_color="color",
                    opacity=0.5,
                    get_width=100,
                )] if show_lines else []),
                *([pdk.Layer(
                    "TextLayer",
                    data=centers,
                    get_position="geometry.coordinates",
                    get_text="name",
                    get_fill_color="[0, 0, 0]",
                    opacity=0.5,
                    get_size=16,
                )] if show_names else []),
            ],
        ))
