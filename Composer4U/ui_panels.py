# -*- coding: utf-8 -*-
# Copyright 2025 Pravin Saravanan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.



import bpy
import os

# Import preferences for API key check
from . import preferences

# Function to draw the common content for both panels
def draw_main_panel_content(self, context, layout):
    module_name_for_prefs = __package__

    addon_prefs = None
    try:
        addon_prefs = context.preferences.addons[module_name_for_prefs].preferences
    except KeyError:
        # This can happen if the add-on is just being enabled or Preferences are not fully loaded
        pass

    # Check if API key is set
    if addon_prefs is None or not addon_prefs.api_key:
        box = layout.box()
        box.label(text="Google Gemini API Key Missing!", icon='ERROR')
        box.label(text="Please set your API key in the Add-on Preferences.")

        row = box.row()
        # CRITICAL FIX: Assign 'module' to the returned operator instance, not in the call
        op = row.operator("preferences.addon_show", text="Set API Key", icon='PREFERENCES')
        op.module = module_name_for_prefs
        # END CRITICAL FIX

        layout.separator()
        layout.label(text="Composition functionality disabled until key is provided.", icon='INFO')
    else:
        # If API key is set, draw the button to open the main UI dialog
        layout.operator("composer4u.open_dialog", icon='OUTLINER_OB_SPEAKER')

# Panel for the 3D Viewport
class COMPOSER4U_PT_MainPanel_3DView(bpy.types.Panel):
    bl_label = "Composer4U"
    bl_idname = "COMPOSER4U_PT_MainPanel_3DView"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Composer4U"

    def draw(self, context):
        layout = self.layout
        draw_main_panel_content(self, context, layout)

# Panel for the Video Sequence Editor
class COMPOSER4U_PT_MainPanel_VSE(bpy.types.Panel):
    bl_label = "Composer4U"
    bl_idname = "COMPOSER4U_PT_MainPanel_VSE"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Composer4U"

    def draw(self, context):
        layout = self.layout
        draw_main_panel_content(self, context, layout)