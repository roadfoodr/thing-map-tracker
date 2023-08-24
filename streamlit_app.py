# -*- coding: utf-8 -*-
"""
Created on Wed May 24 02:35:20 2023

@author: MDP
"""

import pandas as pd
# import numpy as np
import streamlit as st
from streamlit_utilities import check_password as check_password
from streamlit_js_eval import streamlit_js_eval, get_geolocation

import boto3
# from boto3.dynamodb.conditions import Key, Attr
import awswrangler as wr
import uuid
import geohash  # docs: https://github.com/vinsci/geohash/
#                 also: https://docs.quadrant.io/quadrant-geohash-algorithm
#            and maybe: https://www.pluralsight.com/resources/blog/cloud/location-based-search-results-with-dynamodb-and-geohash

import datetime
import pydeck as pdk
import altair as alt
import ast
from streamlit_utilities import rgb_to_hex as rgb_to_hex
from streamlit_utilities import check_duplicate as check_duplicate

boto3.setup_default_session(region_name="us-east-2")

TABLE_NAME = st.secrets['table_name']
THING_NAME = st.secrets['thing_name']

# %% TODOs

# TODO: admin password (delete option)  vs read password
# TODO: "undo" last action (button visible if there is a last_row in state)
# TODO: confirm distance / duplicate thing before adding
# TODO: geohash region containing thing "a" but not thing "b"
# TODO: different thing sizes may require 2 separate layers
# TODO: geomerge to flag with District label
# TODO: compute/wrangle color/size based on mapping from type
# TODO: timezones from timestamp are different on desktop vs mobile
# TODO: compute map center, bounds from data points
#       see https://deckgl.readthedocs.io/en/latest/data_utils.html#pydeck.data_utils.viewport_helpers.compute_view

# %% LOAD DATA ONCE
# TODO: may not want to cache this since this is being handled in session state
@st.cache_data
def load_data(table_name=TABLE_NAME):    
    df = wr.dynamodb.read_items(table_name=table_name, as_dataframe=True,
                                max_items_evaluated=5000)
    colnames = [THING_NAME, 'type', 'create_time', 'username',
                'lat', 'lon', 'geohash', 'ID', 'timestamp', 'u_agent']
    df = df[colnames]
    # df['timestamp'] = pd.to_numeric(df['timestamp'])
    df.sort_values(by='timestamp', ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

# %% utility
def clear_location_info():
    if 'getLocation()' in st.session_state.keys():
            del st.session_state['getLocation()']
            
    location, lat, lon, geoloc, timestamp, dt, dts, id_string = (
        None, 0, 0, None, 0, None, None, '')
    newrow_dict = {}
    return True

# %%  STREAMLIT APP LAYOUT
st.set_page_config(
    layout="centered",       # alternative option: 'wide'
    page_icon=":ballot_box_with_ballot:",
    page_title=st.secrets['page_title'] )

if not check_password():
    st.stop()
    # pass

if "oldrow" not in st.session_state:
    st.session_state["oldrow"] = None
if "getLocation()" not in st.session_state:
    st.session_state["getLocation()"] = None
if "UA" not in st.session_state:
    st.session_state["UA"] = None
u_agent = 'NA'

# %% App title and refresh control

st.write(f"## {st.secrets['app_title']}")
st.write("##### _BETA version - data may be cleared periodically_")

buf, refresh_area = st.columns([5,1])
with refresh_area:
    if st.button('Refresh all'):
        # Delete all the items in Session state
        for key in st.session_state.keys():
            if key not in ["password_correct", "initials_text_input"]:
                del st.session_state[key]
        # hack to prevent this internal field from being cleared along with cache
        initials_text_input_save = ''
        if "initials_text_input" in st.session_state.keys():
            initials_text_input_save = st.session_state['initials_text_input']
        st.cache_data.clear()
        st.session_state['initials_text_input'] = initials_text_input_save
        st.session_state['filter_control'] = 'All'
        st.experimental_rerun()

# %% password has been validated, load and preview data 
if "df" not in st.session_state:
    st.session_state['df'] = load_data()

entries_area = st.empty()
with entries_area.expander('Recent entries', expanded=True):
    st.write(st.session_state['df'].tail(5))

# %% form

buf, initials_area = st.columns([5,1])
with initials_area:
    initials = st.text_input('Your initials', '', max_chars=10, key="initials_text_input")

if not initials:
    st.warning("Initials are blank.  Please enter your initials (or 'test') above.")
    form_submit = False
else:
    with st.form("thing_form", clear_on_submit=False):
        # header = st.columns([2,2])
        # header[0].subheader(st.secrets['thing_type_header'])
        # header[1].subheader(st.secrets['thing_subtype_header'])
        st.write('##### Create entry at current location')
        form_cols = st.columns(2)
        thing_type = form_cols[0].radio(st.secrets['thing_type_header'],
                                   st.secrets['thing_types'],
                                   label_visibility='visible')
        thing_subtype = form_cols[1].radio(st.secrets['thing_subtype_header'],
                                      st.secrets['thing_subtypes'],
                                      label_visibility='visible')
    
        form_submit = st.form_submit_button(f'Add {THING_NAME}')

duplicate_warning_area = st.empty()
last_added_area = st.empty()

# %% form handling
if form_submit:
    # ensure that state is cleared before attempting a new request
    clear_location_info()
    # apparently the library puts these results into session state for later retrieval
    # Returns user's location after asking for permission when the user clicks the generated link with the given text
    location = get_geolocation()
    # u_agent = streamlit_js_eval(
    #     js_expressions='window.navigator.userAgent', 
    #     want_output = True, key = 'UA')
    
# %% location request has returned data and added it to session state
if st.session_state['getLocation()'] is not None:  # This came from the JS call above
    location = st.session_state['getLocation()']
    lat, lon = location['coords']['latitude'], location['coords']['longitude']
    geoloc = geohash.encode(lat, lon, precision=8)

    timestamp = location['timestamp']
    dt = datetime.datetime.fromtimestamp(int(timestamp)/1000)
    dts = dt.strftime('%a, %d %b %Y %H:%M:%S %z')
    id_string = str(uuid.uuid4())
    st.session_state['getLocation()'] = None
        
    # if st.session_state['UA'] is not None:  # This came from the js call above
    #     u_agent = st.session_state['UA']
    #     st.session_state['UA'] = None
    # else:
    #     u_agent = None
    # u_agent = "NA"

    newrow_dict = {'ID':id_string, 
                    THING_NAME:thing_type, 'type':thing_subtype,
                    'lat':str(lat), 'lon':str(lon), 'geohash':geoloc,
                    'create_time':dts, 'timestamp':timestamp,
                    'username':initials, 'u_agent':u_agent}
    # st.write(f'{newrow_dict=}')
    if check_duplicate(st.session_state['df'], geoloc, 
                       THING_NAME, thing_type, thing_subtype):
        duplicate_warning_text = (f'Entry not added: there is already a '
                                  f'{THING_NAME} of type {thing_type}, '
                                  f'{thing_subtype} near this location')
        with duplicate_warning_area.container():
            st.error(duplicate_warning_text)
        st.toast(duplicate_warning_text, icon='❌')
    else:
        # Write to DB
        # Does not seem to be a way to check success?
        # https://aws-sdk-pandas.readthedocs.io/en/stable/stubs/awswrangler.dynamodb.put_items.html
        wr.dynamodb.put_items(items=[newrow_dict], table_name=TABLE_NAME)
        st.toast(f"Added {THING_NAME}: {thing_type}, {thing_subtype}")
        
        # also update local state
        st.session_state['df'] = pd.concat([st.session_state['df'],
                                            pd.DataFrame([newrow_dict])], 
                                            ignore_index=True)
        with entries_area.expander('Recent entries', expanded=True):
            st.write(st.session_state['df'].tail(5))
    
        st.session_state['oldrow'] = newrow_dict
        
    # attempt to sanitize state
    clear_location_info()


# Option to undo the last row added in this session - add button here
if st.session_state['oldrow'] is not None:
    oldrow_dict = st.session_state['oldrow']
    with last_added_area.container():
        st.write(f"_last added: {oldrow_dict[THING_NAME]}, "
                 f"{oldrow_dict['type']}_")

# st.write(st.session_state['df'])
# st.write(st.session_state)


# %% display map controls
map_style_options = { 'mapbox://styles/mapbox/streets-v12': 'Street map', 
                      None: 'Light background',
                      }
map_title_area, filter_control_area, tile_control_area = st.columns([2, 1, 1])
with map_title_area:
    st.write(f"##### Map: {THING_NAME} locations")
with filter_control_area:
    filter_selection = st.selectbox(
            'Filter by:',
            ['All'] + st.secrets['thing_types'],
            key='filter_control'
            )
with tile_control_area:
    map_style = st.radio('Map tiles', map_style_options.keys(),
                            format_func=lambda x: map_style_options[x])


# %% filter df per controls
df_filtered = st.session_state['df']
df_filtered = (df_filtered if filter_selection == 'All'
               else df_filtered[df_filtered[THING_NAME] == filter_selection].copy()
               )

# %% wrangle color (and eventually size) field
mapcols = [THING_NAME, 'type', 'lat', 'lon', 'geohash', 'ID']
df_mapcols = df_filtered[mapcols].copy()
df_mapcols[['lat', 'lon']] = df_mapcols[['lat', 'lon']].apply(
    pd.to_numeric, errors='coerce')

# st.map(data=df_mapcols, zoom=9)

if 'thing_colors' in st.secrets:
    # convert string representation to tuples
    thing_colors = [ast.literal_eval(item) for item in st.secrets['thing_colors']]
    color_lookup = dict(zip(st.secrets['thing_types'], thing_colors))
else:
    # For quick testing: assign a mapping of colors based on THING_NAME
    color_lookup = pdk.data_utils.assign_random_colors(df_mapcols[THING_NAME])
df_mapcols['color'] = df_mapcols.apply(lambda row: 
                                       color_lookup.get(row[THING_NAME]),
                                       axis=1)
# st.write('##### Recent entries')
# st.write(df_mapcols.tail(5))

# %% compute and render the map

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
                # get_fill_color='[222, 44, 0, 88]',
                # get_line_color='[200, 30, 0, 99]',
                get_color='color',
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
        tooltip={"html": "<center><strong>{"+
                 THING_NAME+"}</strong><br>{type}<br>{ID}"+
                 "<br>{lat} | {lon}"},
        # tooltip={"html": "<strong>TOOLTIIP</strong>"},
        # tooltip=True,
        )
    return thing_map

thing_map = construct_thing_map(map_style)
# st.pydeck_chart(thing_map)  # tooltips only work if you display the object directly
thing_map

# %% Charts

st.write(f'#### {THING_NAME.title()} counts _(total: {len(df_filtered)})_')
df_counts = df_filtered[[THING_NAME, 'type']].copy()
df_counts = df_counts.groupby(by=THING_NAME).count()
df_counts.reset_index(inplace=True)
df_counts.rename(columns={'type':'count'}, inplace=True)

df_counts['color'] = df_counts.apply(lambda row: 
                                       color_lookup.get(row[THING_NAME]),
                                       axis=1)
df_counts['hexcolor'] = df_counts['color'].apply(lambda r: rgb_to_hex(*r))

# st.write(df_counts)
st.write(alt.Chart(df_counts).mark_bar().encode(
    x=alt.X(THING_NAME+":N", sort='-y'),
    y='count:Q',
    color=alt.Color(field='hexcolor', type='nominal', scale=None)
))
