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
import sys

bl_info = {
    "name": "Composer4U",
    "author": "PRAVIN", # Your name here
    "version": (1, 0, 0),
    "blender": (4, 0, 0), # Ensure this matches your Blender version (e.g., 4, 1, 0)
    "location": "3D Viewport > Sidebar > Composer4U Tab / VSE > Sidebar > Composer4U Tab",
    "description": "Generate music compositions from text prompts using Google Gemini API.",
    "warning": "Requires Google Gemini API Key. Audio generation uses external API.",
    "doc_url": "",
    "category": "Audio",
}

# Add vendor folder to sys.path
current_dir = os.path.dirname(__file__)
vendor_dir = os.path.join(current_dir, "vendor")
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)
    print(f"Added '{vendor_dir}' to sys.path for Composer4U addon.")

# Import modules
from . import preferences
from . import properties
from . import operators
from . import ui_panels

# List of classes to register/unregister
# IMPORTANT: UIList classes (like COMPOSER4U_UL_History) and their PropertyGroup
# must be registered BEFORE any panels/operators that use them.
classes = (
    properties.COMPOSER4U_AudioHistoryItem,   
    properties.COMPOSER4U_UL_History,         
    preferences.Composer4UAddonPreferences,   
    operators.COMPOSER4U_OT_SendPrompt,
    operators.COMPOSER4U_OT_AddAudioToTimeline, 
    operators.COMPOSER4U_OT_StopGeneration,
    operators.COMPOSER4U_OT_OpenDialog,       
    ui_panels.COMPOSER4U_PT_MainPanel_3DView,
    ui_panels.COMPOSER4U_PT_MainPanel_VSE,
)

def register():
    # Register all classes first
    for cls in classes:
        bpy.utils.register_class(cls)
    # Then register scene properties, which no longer registers classes themselves
    properties.register_scene_properties_only_props()
    # Start the async loop thread when the add-on is registered
    operators._start_async_loop_thread()
    print("Composer4U Addon Registered. Async loop thread started.")

def unregister():
    # Stop the async loop thread when the add-on is unregistered
    operators._stop_async_loop_thread()
    print("Composer4U Addon Unregistered. Async loop thread stopped.")
    # Unregister scene properties in reverse order
    properties.unregister_scene_properties_only_props()
    # Unregister classes in reverse order
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    print("Composer4U Addon Unregistered.")

if __name__ == "__main__":
    register()