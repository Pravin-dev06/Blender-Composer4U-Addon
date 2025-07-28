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

# --- UI List Item for History ---
class COMPOSER4U_AudioHistoryItem(bpy.types.PropertyGroup):
    """Properties for a single item in the audio generation history."""
    text: bpy.props.StringProperty(
        name="History Entry",
        description="Text of the history entry (prompt or response)",
        default=""
    )

# --- UI List for History Display ---
class COMPOSER4U_UL_History(bpy.types.UIList):
    """UIList for displaying the audio generation history."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.text, icon='TEXT')
        elif self.layout_type in {'GRID'}:
            layout.label(text=item.text, icon='TEXT')

# --- Scene Properties Registration Functions ---
def register_scene_properties_only_props():
    # Link custom properties directly to the scene
    bpy.types.Scene.composer4u_input = bpy.props.StringProperty(
        name="Prompt",
        description="Enter your text prompt for music generation",
        default="",
        maxlen=100000
    )
    bpy.types.Scene.composer4u_history = bpy.props.CollectionProperty(type=COMPOSER4U_AudioHistoryItem)
    bpy.types.Scene.composer4u_index = bpy.props.IntProperty(name="History Index")
    bpy.types.Scene.composer4u_last_audio_path = bpy.props.StringProperty(
        name="Last Audio Path",
        description="Path to the last generated audio file",
        subtype='FILE_PATH',
        default=""
    )
    # NEW: Property for user-defined output folder
    bpy.types.Scene.composer4u_output_folder = bpy.props.StringProperty(
        name="Output Folder",
        description="Folder to save generated audio files. Leave empty to use a temporary location.",
        subtype='DIR_PATH', # This will give a folder picker in the UI
        default=""
    )


def unregister_scene_properties_only_props():
    # Unregister in reverse order of how they were linked
    del bpy.types.Scene.composer4u_output_folder # NEW: Unregister the new property
    del bpy.types.Scene.composer4u_last_audio_path
    del bpy.types.Scene.composer4u_index
    del bpy.types.Scene.composer4u_history
    del bpy.types.Scene.composer4u_input