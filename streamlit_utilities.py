# -*- coding: utf-8 -*-
"""
Created on Thu May 25 00:56:32 2023

@author: MDP
"""

import streamlit as st


CalcColors = ['#2f78b3', # 47, 120, 179  Blue
                   '#6babd0', # 107, 171, 208
                   '#f2efee', # 242, 239, 238 Gray
                   '#e48169', # 228, 129, 105
                   '#bf363a', # 191, 54, 58   Red
                   ]

def hex_to_rgb(hex):
  return [int(hex[i:i+2], 16) for i in (0, 2, 4)]



def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct.
        return True
