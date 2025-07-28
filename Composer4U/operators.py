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
import asyncio
import wave
import tempfile
import sys
import threading
import time
import datetime # For generating unique filenames
import traceback # Added for detailed error reporting
import concurrent.futures # Import for concurrent.futures.CancelledError

# Import classes defined in properties.py and preferences.py
from . import properties
from . import preferences

# --- PYAUDIO IMPORT ---
try:
    import pyaudio
except ImportError:
    print("Composer4U Error: pyaudio library not found. Real-time playback will be disabled.")
    pyaudio = None # Set to None if not available


try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Composer4U Error: Google Generative AI library not found. Please check your 'vendor' folder setup.")
    genai = None # Set to None to prevent further errors


# --- Common Configuration ---
FORMAT_WAV_BITS = 16
FORMAT_PYAUDIO = pyaudio.paInt16 if pyaudio else None
CHANNELS = 2
OUTPUT_RATE = 48000
MODEL = 'models/lyria-realtime-exp'
CHUNK_SIZE_PYAUDIO = 4200 # This chunk size is for pyaudio internal buffer, not necessarily for API chunks
VSE_channel = 1 # Default VSE channel for audio strips

# --- Global asyncio loop and task management ---
_async_thread = None
_async_loop_running = False
_async_tasks = []
_background_loop = None


def _start_async_loop_thread():
    global _async_thread, _async_loop_running, _background_loop
    if _async_thread and _async_thread.is_alive():
        return

    _async_loop_running = True
    def run_loop():
        global _background_loop
        _background_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_background_loop)
        while _async_loop_running:
            # Allows other tasks/coroutines to run if they are ready
            _background_loop.run_until_complete(asyncio.sleep(0.01)) 
            # Clean up completed tasks
            global _async_tasks
            _async_tasks = [task for task in _async_tasks if not task.done()]
        _background_loop.close()
        _background_loop = None

    _async_thread = threading.Thread(target=run_loop, daemon=True)
    _async_thread.start()


def _stop_async_loop_thread():
    global _async_loop_running
    _async_loop_running = False


def _submit_async_task_to_background(coro):
    if not (_async_thread and _async_thread.is_alive()):
        _start_async_loop_thread()
    # Wait until the event loop is actually running in the background thread
    while _background_loop is None:
        time.sleep(0.01)
    future = asyncio.run_coroutine_threadsafe(coro, _background_loop)
    _async_tasks.append(future)
    return future


# --- Operator to add audio to the Video Sequence Editor ---
class COMPOSER4U_OT_AddAudioToTimeline(bpy.types.Operator):
    bl_idname = "composer4u.add_audio_to_timeline"
    bl_label = "Add Audio to VSE" 
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(
        name="Audio File Path",
        description="Path to the audio file to add to the Video Sequence Editor",
        subtype='FILE_PATH'
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        self.report({'INFO'}, f"AddAudioToVSE: Attempting to add audio. Received filepath: {self.filepath}")
        print(f"DEBUG: AddAudioToVSE - Received filepath: {self.filepath}")

        if not self.filepath or not os.path.exists(self.filepath):
            self.report({'ERROR'}, "Audio file path is invalid or file does not exist.")
            print(f"ERROR: AddAudioToVSE - File does not exist or path is empty: {self.filepath}")
            return {'CANCELLED'}

        absolute_audio_filepath = bpy.path.abspath(self.filepath)
        print(f"DEBUG: AddAudioToVSE - Absolute filepath: {absolute_audio_filepath}")
        print(f"DEBUG: AddAudioToVSE - Does file exist at absolute path? {os.path.exists(absolute_audio_filepath)}")

        if not os.path.exists(absolute_audio_filepath):
            self.report({'ERROR'}, f"File does NOT exist at {absolute_audio_filepath}!")
            print(f"ERROR: AddAudioToVSE - Confirmed file missing after abspath: {absolute_audio_filepath}")
            return {'CANCELLED'}
        
        file_size = os.path.getsize(absolute_audio_filepath)
        print(f"DEBUG: AddAudioToVSE - File size at absolute path: {file_size} bytes")
        if file_size == 0:
            self.report({'WARNING'}, f"Audio file at {absolute_audio_filepath} is empty (0 bytes).")
            print(f"WARNING: AddAudioToVSE - File is empty: {absolute_audio_filepath}")

        # --- IMPORTANT NEW CHECK: Verify WAV integrity before adding ---
        try:
            with wave.open(absolute_audio_filepath, 'rb') as wf:
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                
                print(f"DEBUG: AddAudioToVSE - WAV properties: Channels={nchannels}, SampleWidth={sampwidth}, FrameRate={framerate}, NumFrames={nframes}")
                
                if nframes == 0:
                    self.report({'WARNING'}, "Generated WAV has 0 frames. It might be too short or corrupted.")
                    print("WARNING: AddAudioToVSE - WAV file has 0 frames, likely too short/corrupted for playback.")
                    
        except wave.Error as we:
            self.report({'ERROR'}, f"Invalid WAV file detected: {we}")
            print(f"ERROR: AddAudioToVSE - Invalid WAV file detected at {absolute_audio_filepath}: {we}")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error checking WAV file integrity: {e}")
            print(f"ERROR: AddAudioToVSE - Generic error checking WAV: {e}")
            return {'CANCELLED'}
        # --- END NEW CHECK ---

        scene = context.scene

        try:
            # Ensure sequence_editor exists for adding sound strips
            if not scene.sequence_editor:
                scene.sequence_editor_create()
                print("DEBUG: AddAudioToVSE - Created sequence editor for scene audio management.")

            # Remove existing sound strips that might interfere with scene playback
            for strip in [s for s in scene.sequence_editor.sequences_all if s.type == 'SOUND' and s.name.startswith("Composer4U_Scene_Music")]:
                scene.sequence_editor.sequences.remove(strip)
            print("DEBUG: AddAudioToVSE - Removed previous 'Composer4U_Scene_Music' strips.")


            # --- This is the key: Add the sound using the VSE's sequence_editor ---

            new_sound_strip = scene.sequence_editor.sequences.new_sound(
                name="Composer4U_Scene_Music", # Give it a specific name to identify it later
                filepath=absolute_audio_filepath,
                channel=VSE_channel, # Use the default channel defined earlier or allow user to set it 
                frame_start=1
            )
            
            self.report({'INFO'}, f"Added '{os.path.basename(absolute_audio_filepath)}' to VSE.")
            print(f"DEBUG: AddAudioToVSE - Successfully added '{os.path.basename(absolute_audio_filepath)}' to VSE.")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to add audio to VSE: {e}")
            print(f"ERROR: AddAudioToVSE - Failed to add audio to VSE: {e}")
            traceback.print_exc(file=sys.stderr) 
            return {'CANCELLED'}
        return {'FINISHED'}

# --- Operator to Stop Music Generation ---
class COMPOSER4U_OT_StopGeneration(bpy.types.Operator):
    bl_idname = "composer4u.stop_generation"
    bl_label = "Stop Generation"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return COMPOSER4U_OT_SendPrompt._async_task_future is not None and \
               not COMPOSER4U_OT_SendPrompt._async_task_future.done()

    def execute(self, context):
        if COMPOSER4U_OT_SendPrompt._async_task_future:
            COMPOSER4U_OT_SendPrompt._async_task_future.cancel()
            self.report({'INFO'}, "Sent stop request to music generation task.")
            print("DEBUG: StopGeneration - Sent stop request.")
            return {'FINISHED'}
        return {'CANCELLED'}


# --- Send Prompt Operator (Modal) ---
class COMPOSER4U_OT_SendPrompt(bpy.types.Operator):
    bl_idname = "composer4u.send_prompt"
    bl_label = "Generate Composition"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _async_task_future = None
    _result_container = {} # Container to get results back from the async task

    @classmethod
    def poll(cls, context):
        if genai is None: return False
        addon_prefs = context.preferences.addons[__package__].preferences # Use the correct preferences class
        return bool(addon_prefs.api_key) and (cls._async_task_future is None or cls._async_task_future.done())

    def invoke(self, context, event):
        addon_prefs = context.preferences.addons[__package__].preferences # Use the correct preferences class
        if not addon_prefs.api_key:
            self.report({'ERROR'}, "Google Gemini API Key not set.")
            return {'CANCELLED'}

        scene = context.scene
        prompt = scene.composer4u_input.strip()
        output_folder = scene.composer4u_output_folder.strip()

        if not prompt:
            self.report({'WARNING'}, "Prompt is empty.")
            return {'CANCELLED'}
        if output_folder and not os.path.isdir(output_folder):
            self.report({'ERROR'}, "Output folder is invalid.")
            return {'CANCELLED'}

        scene.composer4u_history.add().text = f"Prompt: {prompt}"
        scene.composer4u_input = ""
        scene.composer4u_last_audio_path = ""
        scene.composer4u_index = len(scene.composer4u_history) - 1
        
        self.report({'INFO'}, "Generating music...")
        print("DEBUG: SendPrompt - Starting music generation...")
        
        # Reset the result container and submit the task
        self._result_container.clear()
        COMPOSER4U_OT_SendPrompt._async_task_future = _submit_async_task_to_background(
            self._generate_music_async(addon_prefs.api_key, prompt, output_folder, self._result_container)
        )
        
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        future = COMPOSER4U_OT_SendPrompt._async_task_future
        
        if not (future and future.done()):
            return {'PASS_THROUGH'}

        audio_filepath = None
        message_for_user = "Generation finished." # Default success message

        try:
            future.result() # This will re-raise any exception from _generate_music_async
            audio_filepath = self._result_container.get('audio_filepath')
            # If _generate_music_async set a specific message, use it
            message_for_user = self._result_container.get('message', "Music generated successfully.")
            print(f"DEBUG: Modal - Async task completed. Audio path from result_container: {audio_filepath}")

        except Exception as e:
            # MODIFIED: Check for both asyncio.CancelledError and concurrent.futures.CancelledError
            if isinstance(e, (asyncio.CancelledError, concurrent.futures.CancelledError)):
                audio_filepath = self._result_container.get('audio_filepath') # Path to the *partial* file
                message_for_user = "Generation stopped by user."
                self.report({'INFO'}, "Generation stopped.")
                print("DEBUG: Modal - Generation was cancelled.")
                
                # --- NEW LOGIC: Automatically add partial file to VSE on stop ---
                if audio_filepath and os.path.exists(audio_filepath) and os.path.getsize(audio_filepath) > 0:
                    context.scene.composer4u_last_audio_path = audio_filepath # Ensure path is set for later reference
                    # Use bpy.ops to call the operator that adds to VSE
                    # This must be done from the main thread (modal operator context)
                    bpy.ops.composer4u.add_audio_to_timeline(filepath=audio_filepath)
                    self.report({'INFO'}, "Partial audio loaded into VSE.")
                    print(f"DEBUG: Modal - Auto-loaded partial audio into VSE: {audio_filepath}")
                else:
                    self.report({'WARNING'}, "Generation stopped, but no partial audio file was saved or it was empty.")
                    print("WARNING: Modal - No partial audio file saved/found/empty after stop.")
                # --- END NEW LOGIC ---

            else:
                # Handle all other unexpected exceptions as errors
                message_for_user = f"Error: {e}"
                self.report({'ERROR'}, f"Music generation failed: {e}")
                print(f"ERROR: Modal - Music generation failed with unexpected exception: {e}")
                traceback.print_exc(file=sys.stderr) # Print full traceback to console

        # Final check and update of the scene property based on generation outcome
        if audio_filepath and os.path.exists(audio_filepath) and os.path.getsize(audio_filepath) > 0:
            context.scene.composer4u_last_audio_path = audio_filepath
            print(f"DEBUG: Modal - Final audio file path set to scene property: {audio_filepath}")
        else:
            # If it was an error (not cancellation) or an empty file despite successful generation
            if "Error" in message_for_user or "No audio file" in message_for_user:
                context.scene.composer4u_last_audio_path = "" # Clear path if it was an error or empty
            # If it was a cancellation with no file, the above new logic already handles reporting
            print("DEBUG: Modal - No valid audio file path to set to scene property after modal processing.")


        # Add the final message to history
        context.scene.composer4u_history.add().text = f"Composer4U: {message_for_user}"
        context.scene.composer4u_index = len(context.scene.composer4u_history) - 1
        
        self._cleanup(context) # Clean up timer and future
        context.area.tag_redraw() # Force UI redraw
        print("DEBUG: Modal - Finished processing modal event.")
        return {'FINISHED'} # Exit modal operator

    def cancel(self, context):
        # Called if user presses ESC or clicks outside pop-up (if invoke_props_dialog)
        if COMPOSER4U_OT_SendPrompt._async_task_future and not COMPOSER4U_OT_SendPrompt._async_task_future.done():
            COMPOSER4U_OT_SendPrompt._async_task_future.cancel()
            self.report({'INFO'}, "Generation cancelled by user (dialog closed).")
            print("DEBUG: Cancel - Async task cancelled via cancel method.")
        self._cleanup(context)

    def _cleanup(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
            print("DEBUG: Cleanup - Timer removed.")
        COMPOSER4U_OT_SendPrompt._async_task_future = None
        print("DEBUG: Cleanup - Async task future cleared.")

    async def _generate_music_async(self, api_key, prompt_text, output_folder, result_container):
        audio_filepath = None
        wav_writer = None
        p_audio = None
        output_stream = None
        
        # Flag to indicate if generation was naturally completed or cancelled by user
        was_cancelled = False 

        print(f"DEBUG: _generate_music_async - Starting async generation for prompt: '{prompt_text[:50]}...'")

        try:
            if output_folder and os.path.isdir(output_folder):
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                # Sanitize prompt for filename, truncate to avoid excessively long names
                sanitized_prompt = "".join(c if c.isalnum() else "_" for c in prompt_text[:30]).strip("_") or "music"
                filename = f"composition_{timestamp}_{sanitized_prompt}.wav"
                audio_filepath = os.path.join(output_folder, filename)
            else:
                # Use a proper temporary file that gets a unique name immediately
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, mode='wb') as temp_f:
                    audio_filepath = temp_f.name
                
            result_container['audio_filepath'] = audio_filepath # Store path for modal handler
            self.report({'INFO'}, f"Audio will be saved to: {audio_filepath}")
            print(f"DEBUG: _generate_music_async - Determined output path: {audio_filepath}")

            client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
            
            # Initialize PyAudio only if available
            if pyaudio and FORMAT_PYAUDIO:
                p_audio = pyaudio.PyAudio()
                output_stream = p_audio.open(format=FORMAT_PYAUDIO, channels=CHANNELS, rate=OUTPUT_RATE, output=True)
                print("DEBUG: _generate_music_async - PyAudio stream opened.")
            else:
                print("DEBUG: _generate_music_async - PyAudio not available, skipping real-time playback.")

            # IMPORTANT: Ensure wave.open is inside the try block for proper cleanup
            wav_writer = wave.open(audio_filepath, 'wb')
            wav_writer.setnchannels(CHANNELS)
            wav_writer.setsampwidth(FORMAT_WAV_BITS // 8) # Bytes per sample (e.g., 2 for 16-bit)
            wav_writer.setframerate(OUTPUT_RATE)
            print(f"DEBUG: _generate_music_async - WAV writer opened for {audio_filepath}.")

            async with client.aio.live.music.connect(model=MODEL) as session:
                print("DEBUG: _generate_music_async - Connected to Generative AI session.")
                await session.set_weighted_prompts(prompts=[types.WeightedPrompt(text=prompt_text, weight=1.0)])
                await session.play()
                print("DEBUG: _generate_music_async - Session play initiated.")

                # Loop to continuously receive audio chunks
                async for message in session.receive():
                    if asyncio.current_task().cancelled():
                        print("DEBUG: _generate_music_async - Task cancelled, breaking loop.")
                        was_cancelled = True # Set cancellation flag
                        break # Exit the async for loop immediately

                    if message.server_content:
                        chunk = message.server_content.audio_chunks[0].data
                        wav_writer.writeframes(chunk) # Write raw audio bytes to WAV file
                        if output_stream: # Only write to pyaudio if stream is successfully opened
                            output_stream.write(chunk) # Play raw audio bytes
                    elif message.filtered_prompt:
                        # If the prompt was filtered by the API, raise an error
                        raise Exception(f"Prompt filtered by API: {message.filtered_prompt.reason}")
            
            # This block is reached if the 'async for' loop completes (either naturally or by break)
            if not was_cancelled:
                # If generation finished without being cancelled, set success message
                result_container['message'] = "Music generated successfully."
                self.report({'INFO'}, "Music generation finished successfully.")
                print("DEBUG: _generate_music_async - Generation loop completed naturally.")
            else:
                # If it was cancelled, the modal handler will pick up the CancelledError
                # and set its own message. We don't need to set result_container['message'] here.
                print("DEBUG: _generate_music_async - Generation loop broken by cancellation.")

        except Exception as e:
            print(f"ERROR: _generate_music_async - An error occurred during generation: {e}")
            traceback.print_exc(file=sys.stderr) # Print full traceback for debugging
            
            # --- IMPORTANT: Only remove the file if it's NOT a CancelledError ---
            # We want to keep partial audio on user cancellation
            # MODIFIED: Check for both asyncio.CancelledError and concurrent.futures.CancelledError
            if isinstance(e, (asyncio.CancelledError, concurrent.futures.CancelledError)):
                print("DEBUG: _generate_music_async - Handling CancelledError. Keeping partial audio file.")
                # The 'finally' block will close the WAV writer, hopefully finalizing the header.
                # No need to raise it again here, as the outer modal handler expects it.
            else:
                # For any other *unexpected* error, remove the potentially corrupted file
                if audio_filepath and os.path.exists(audio_filepath):
                    try: 
                        os.remove(audio_filepath)
                        print(f"DEBUG: _generate_music_async - Removed partially written file due to unexpected error: {audio_filepath}")
                    except OSError as ose: 
                        print(f"WARNING: _generate_music_async - Could not remove file {audio_filepath} after error: {ose}")
                result_container['audio_filepath'] = None # Clear path if not a valid output
                # Re-raise the exception for the modal handler to catch as a general error
                raise e 
        finally:
            # Ensure all resources are closed, regardless of success or error
            if wav_writer: 
                wav_writer.close() # This is crucial for finalizing the WAV header
                print("DEBUG: _generate_music_async - WAV writer closed.")
            if output_stream:
                output_stream.stop_stream()
                output_stream.close()
                print("DEBUG: _generate_music_async - PyAudio stream stopped and closed.")
            if p_audio: 
                p_audio.terminate()
                print("DEBUG: _generate_music_async - PyAudio terminated.")
            print("DEBUG: _generate_music_async - Finally block completed.")


# --- Pop-up Dialog Operator ---
# This operator is used to display the UI in a popup window.
# The UI content itself is drawn using the draw method.
class COMPOSER4U_OT_OpenDialog(bpy.types.Operator):
    bl_idname = "composer4u.open_dialog"
    bl_label = "Open Composer4U"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=600)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Use properties from the scene directly as they are registered there
        layout.label(text="Composition History:", icon='INFO')
        layout.template_list("COMPOSER4U_UL_History", "", scene, "composer4u_history", scene, "composer4u_index", rows=10)
        
        is_generating = COMPOSER4U_OT_SendPrompt._async_task_future and not COMPOSER4U_OT_SendPrompt._async_task_future.done()
        
        row = layout.row(align=True)
        if is_generating:
            row.label(text="Generating...", icon='TIME')
            row.operator("composer4u.stop_generation", text="Stop", icon='CANCEL')
        else:
            col = row.column(align=True)
            col.prop(scene, "composer4u_input", text="", icon='TEXT')
            col.prop(scene, "composer4u_output_folder", text="")
            row.operator("composer4u.send_prompt", text="Generate", icon='EXPERIMENTAL')
        
        if scene.composer4u_last_audio_path and os.path.exists(scene.composer4u_last_audio_path):
            layout.separator()
            box = layout.box()
            box.label(text="Last Generated Audio:", icon='SOUND')
            row = box.row(align=True)
            row.label(text=os.path.basename(scene.composer4u_last_audio_path), icon='FILE_SOUND')
            op = row.operator("composer4u.add_audio_to_timeline", text="Add to VSE", icon='PLAY_SOUND') 
            op.filepath = scene.composer4u_last_audio_path
        elif not is_generating:
            layout.label(text="No audio generated yet.", icon='INFO')

    def execute(self, context):
        return {'FINISHED'}