# -*- coding: utf-8 -*-
"""
Created on Wed May 24 02:35:20 2023

@author: MDP
"""

import pandas as pd
import numpy as np
import streamlit as st
from streamlit_utilities import check_password as check_password
from streamlit_js_eval import streamlit_js_eval, get_geolocation

import boto3
# from boto3.dynamodb.conditions import Key, Attr
import awswrangler as wr
import geohash  # docs: https://github.com/vinsci/geohash/
#                 also: https://docs.quadrant.io/quadrant-geohash-algorithm
#            and maybe: https://www.pluralsight.com/resources/blog/cloud/location-based-search-results-with-dynamodb-and-geohash

# import random
import datetime
import pydeck as pdk

TABLE_NAME = st.secrets['table_name']
THING_NAME = st.secrets['thing_name']

# %% TODOs

# TODO: specify tracked type/subtype from config file, also table name
#                    (actually specify config options via another table name)
# TODO: admin password (delete option)  vs read password
# TODO: "undo" last action (button visible if there is a last_row in state)
# TODO: confirm distance / duplicate thing before adding
# TODO: count things of given type within distance, delete them
# TODO: filter dataset by thing type (checkboxes for pairs?)
# TODO: thing sizes may require 2 separate layers
# TODO: add hover tooltip for thing
# TODO: geomerge to flag with District label
# TODO: compute/wrangle color/size based on mapping from type

# %% LOAD DATA ONCE
@st.cache_data
def load_data(table_name=TABLE_NAME):    
    df = wr.dynamodb.read_items(table_name=table_name, allow_full_scan=True)
    colnames = ['ID', THING_NAME, 'type', 'create_time', 'username',
                'lat', 'lon', 'geohash', 'timestamp', 'u_agent']
    df = df[colnames]
    # df['timestamp'] = pd.to_numeric(df['timestamp'])
    df.sort_values(by='timestamp', ascending=True, inplace=True)
    
    return df

# %%  STREAMLIT APP LAYOUT
st.set_page_config(
    layout="centered",       # alternative option: 'wide'
    page_icon=":ballot_box_with_ballot:",
    page_title=st.secrets['page_title'] )

map_style = 'mapbox://styles/mapbox/streets-v12'
boto3.setup_default_session(region_name="us-east-2")

if not check_password():
    # st.stop()
    pass

if "newrow" not in st.session_state:
    st.session_state["newrow"] = None
if "oldrow" not in st.session_state:
    st.session_state["oldrow"] = None
if "getLocation()" not in st.session_state:
    st.session_state["getLocation()"] = None
if "UA" not in st.session_state:
    st.session_state["UA"] = None

# %% password has been validated, load and preview data 
df = load_data()
if "df" not in st.session_state:
    st.session_state["df"] = df
    
sample_area, refresh_area = st.columns([7,1])
with sample_area:
    st.write("##### Sample of data")
with refresh_area:
    if st.button('Refresh'):
        st.cache_data.clear()
        st.experimental_rerun()

st.dataframe(df.tail(5))
# st.write(df.dtypes)

# %% form

title_area, initials_area = st.columns([7,1])
with title_area:
    st.write(f"## {st.secrets['app_title']}")
with initials_area:
    initials = st.text_input('Your initials', '', max_chars=5)

if not initials:
    st.warning("Initials are blank.  Please enter your initials (or 'test') above.")
    form_submit = False
else:
    with st.form("thing_form", clear_on_submit=True):
        # header = st.columns([2,2])
        # header[0].subheader(st.secrets['thing_type_header'])
        # header[1].subheader(st.secrets['thing_subtype_header'])
    
        row1 = st.columns([2,2])
        thing_type = row1[0].radio(st.secrets['thing_type_header'],
                                   st.secrets['thing_types'],
                                   label_visibility='visible')
        thing_subtype = row1[1].radio(st.secrets['thing_subtype_header'],
                                      st.secrets['thing_subtypes'],
                                      label_visibility='visible')
    
        form_submit = st.form_submit_button('Submit')
    

if form_submit:
    # apparently the library puts these results into session state for later retrieval
    # Returns user's location after asking for permission when the user clicks the generated link with the given text
    location = get_geolocation()
    u_agent = streamlit_js_eval(
        js_expressions='window.navigator.userAgent', 
        want_output = True, key = 'UA')
    if not initials:
        st.toast("Input accepted, but don't forget to enter your initials")
    
if st.session_state['getLocation()'] is not None:  # This came from the JS call above
    location = st.session_state['getLocation()']
    lat, lon = location['coords']['latitude'], location['coords']['longitude']
    geoloc = geohash.encode(lat, lon, precision=8)
    geoloc_decode = geohash.decode(geoloc)

    timestamp = location['timestamp']
    dt = datetime.datetime.fromtimestamp(int(timestamp)/1000)
    dts = dt.strftime('%a, %d %b %Y %H:%M:%S %z')
    id_string = f'{geoloc}|{str(timestamp)[-4:]}'
    st.session_state['getLocation()'] = None
        
    if st.session_state['UA'] is not None:  # This came from the js call above
        u_agent = st.session_state['UA']
        st.session_state['UA'] = None
    else:
        u_agent = None

    newrow_dict = {'ID':id_string, 
                    THING_NAME:thing_type, 'type':thing_subtype,
                    'lat':str(lat), 'lon':str(lon), 'geohash':geoloc,
                    'create_time':dts, 'timestamp':timestamp,
                    'username':initials, 'u_agent':u_agent}
    # st.write(f'{newrow_dict=}')
    st.session_state['newrow'] = newrow_dict


if st.session_state['newrow'] is not None:
    # Write to DB
    # Does not seem to be a way to check success?
    # https://aws-sdk-pandas.readthedocs.io/en/stable/stubs/awswrangler.dynamodb.put_items.html
    
    item = st.session_state['newrow']
    # st.write(item)
    wr.dynamodb.put_items(items=[item], table_name=TABLE_NAME)

    
    st.toast(f"Added {THING_NAME}: {thing_type}, {thing_subtype}")
    # also update local state
    newrow_df = pd.DataFrame([newrow_dict])
    st.session_state['df'] = pd.concat([st.session_state['df'],
                                        newrow_df], 
                                        ignore_index=True)

    st.session_state['oldrow'] = st.session_state['newrow']
    st.session_state['newrow'] = None

# Option to undo the last row added in this session - add button here
if st.session_state['oldrow'] is not None:
    oldrow_dict = st.session_state['oldrow']
    buf, undo_area = st.columns([3,2])
    with undo_area:
        st.write(f"_last added: {oldrow_dict[THING_NAME]}, "
                 f"{oldrow_dict['type']}_")

# st.write(st.session_state['df'])
# st.write(st.session_state)


# %% display map
st.write(f"##### Map: {THING_NAME} locations")

# st.map(data=st.session_state['df'], zoom=9)

df_mapcols = st.session_state['df'][['lat', 'lon', 'sign', 'type', 'geohash']].copy()
df_mapcols[['lat', 'lon']] = df_mapcols[['lat', 'lon']].apply(
    pd.to_numeric, errors='coerce')

st.write(df_mapcols.head(10))

map_style_options = { 'mapbox://styles/mapbox/streets-v12': 'Street map', 
                      None: 'Light background',
                      }
map_style = st.radio('Map tiles', map_style_options.keys(),
                        format_func=lambda x: map_style_options[x])

# we do not want to cache this
# @st.cache_resource
def construct_thing_map(map_style):
    thing_map = pdk.Deck(
        # map_style=None,
        map_style=map_style,
        layers=[
            pdk.Layer(
                'ScatterplotLayer',
                auto_highlight=False,
                pickable=True,
                data=df_mapcols,
                get_position='[lon, lat]',
                get_fill_color='[222, 44, 0, 88]',
                get_line_color='[200, 30, 0, 99]',
                # get_color='color',
                # get_radius='size', # this should work https://pydeck.gl/gallery/scatterplot_layer.html
                get_radius=33,
                radius_min_pixels=3.5,  # https://pydeck.gl/gallery/scatterplot_layer.html
                radius_max_pixels=70,  

                ),
            ],
        initial_view_state=pdk.ViewState(
            latitude=38.00,
            longitude=-78.517,
            zoom=9,
            # pitch=50,
            ),
        tooltip={"html": "<center><strong>{sign}</strong><br>{type}</center>"},
        # tooltip={"html": "<strong>TOOLTIIP</strong>"},
        # tooltip=True,
        )
    return thing_map

thing_map = construct_thing_map(map_style)
# st.pydeck_chart(thing_map)  # tooltips only work if you display the object directly
thing_map