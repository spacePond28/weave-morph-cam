bl_info = {
    "name": "WeaveCameraMorph",
    "description": "Morph between multiple cameras smoothly.",
    "author": "Weave Creative",
    "version": (1, 3, 0), # Incremented version
    "blender": (2, 80, 0),
    "location": "View3D > Add > Camera > Add Morph Camera",
    "category": "Object",
}

import bpy
from bpy.props import PointerProperty, CollectionProperty, FloatProperty, IntProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList
from mathutils import Vector, Euler
import functools # For persistent handlers

# --- Property Group for the List ---
class MorphListItem(PropertyGroup):
    camera: PointerProperty(
        name="Camera",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'CAMERA' and not obj.get("is_morph_camera", False) # Prevent adding morph cam itself
    )

# --- UI List ---
class MORPHCAMERA_UL_CameraList(UIList):
    bl_idname = "MORPHCAMERA_UL_CameraList"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = active_data # The Morph Camera Object
        cam_item = item.camera

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if cam_item:
                 # Use camera icon if valid, else alert icon
                icon = 'CAMERA_DATA' if cam_item.type == 'CAMERA' else 'ERROR'
                layout.prop(item, "camera", text="", icon=icon, emboss=False)
            else:
                layout.prop(item, "camera", text="", icon='QUESTION', emboss=False) # Indicate empty slot

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            if cam_item:
                icon = 'CAMERA_DATA' if cam_item.type == 'CAMERA' else 'ERROR'
                layout.prop(item, "camera", text="", icon=icon, emboss=False)
            else:
                layout.prop(item, "camera", text="", icon='QUESTION', emboss=False)

# --- Operators ---
class AddMorphCameraOperator(Operator):
    bl_idname = "object.add_morph_camera"
    bl_label = "Add Morph Camera"
    bl_description = "Adds a new camera object designed for morphing"

    def execute(self, context):
        scene = context.scene
        loc = scene.cursor.location
        rot = (0.0, 0.0, 0.0)

        # Check if a morph camera already exists (optional, maybe allow multiple?)
        existing_morph_cams = [o for o in scene.objects if o.get("is_morph_camera")]
        if existing_morph_cams:
            self.report({'WARNING'}, "A Morph Camera already exists in the scene.")
            # You could choose to select it or prevent creating another one
            # return {'CANCELLED'}

        morph_camera_data = bpy.data.cameras.new(name="MorphCameraData")
        morph_camera_obj = bpy.data.objects.new(name="MorphCamera", object_data=morph_camera_data)
        morph_camera_obj.location = loc
        morph_camera_obj.rotation_euler = rot
        morph_camera_obj["is_morph_camera"] = True # Use custom property identifier

        scene.collection.objects.link(morph_camera_obj)

        # Make it the active object and active camera
        context.view_layer.objects.active = morph_camera_obj
        morph_camera_obj.select_set(True)
        scene.camera = morph_camera_obj

        # Initialize properties directly on the object
        morph_camera_obj.morph_props.is_morph_camera = True # Use the property group flag

        self.report({'INFO'}, "Morph Camera added.")
        return {'FINISHED'}

class AddSelectedCamerasToListOperator(Operator):
    bl_idname = "morph_list.add_selected_cameras"
    bl_label = "Add Selected Cameras"
    bl_description = "Adds selected valid cameras to the morph list"

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'CAMERA' and obj.get("is_morph_camera")

    def execute(self, context):
        morph_cam_obj = context.object
        morph_props = morph_cam_obj.morph_props
        selected_cameras = [
            cam for cam in context.selected_objects
            if cam.type == 'CAMERA' and cam != morph_cam_obj and not cam.get("is_morph_camera")
        ]

        if not selected_cameras:
            self.report({'INFO'}, "No suitable cameras selected (ensure they are not the Morph Camera itself).")
            return {'CANCELLED'}

        added_count = 0
        for selected_camera in selected_cameras:
            # Avoid duplicates
            if selected_camera not in [item.camera for item in morph_props.morph_list]:
                item = morph_props.morph_list.add()
                item.camera = selected_camera
                added_count += 1

        if added_count > 0:
            morph_props.active_morph_camera_index = len(morph_props.morph_list) - 1
            update_slider_range(context.scene)
            # Trigger immediate update if possible
            if context.scene.camera == morph_cam_obj:
                 trigger_morph_update(context.scene, morph_cam_obj)
            self.report({'INFO'}, f"Added {added_count} camera(s).")
        else:
             self.report({'INFO'}, "Selected camera(s) already in list.")

        return {'FINISHED'}

class AddCameraToListOperator(Operator):
    bl_idname = "morph_list.add_camera"
    bl_label = "Add Empty Slot"
    bl_description = "Adds an empty slot to the morph list to assign a camera manually"

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'CAMERA' and obj.get("is_morph_camera")

    def execute(self, context):
        morph_cam_obj = context.object
        morph_props = morph_cam_obj.morph_props
        item = morph_props.morph_list.add()
        item.camera = None # Add an empty item
        morph_props.active_morph_camera_index = len(morph_props.morph_list) - 1
        update_slider_range(context.scene)
        # Trigger immediate update if possible
        if context.scene.camera == morph_cam_obj:
            trigger_morph_update(context.scene, morph_cam_obj)
        return {'FINISHED'}

class RemoveCameraFromListOperator(Operator):
    bl_idname = "morph_list.remove_camera"
    bl_label = "Remove Camera"
    bl_description = "Removes the selected camera from the morph list"

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'CAMERA' and obj.get("is_morph_camera") and len(obj.morph_props.morph_list) > 0

    def execute(self, context):
        morph_cam_obj = context.object
        morph_props = morph_cam_obj.morph_props
        index = morph_props.active_morph_camera_index

        if 0 <= index < len(morph_props.morph_list):
            morph_props.morph_list.remove(index)
            # Adjust index safely
            morph_props.active_morph_camera_index = min(max(0, index -1), len(morph_props.morph_list) - 1)
            update_slider_range(context.scene)
            # Trigger immediate update if possible
            if context.scene.camera == morph_cam_obj:
                trigger_morph_update(context.scene, morph_cam_obj)
        else:
            self.report({'WARNING'}, "No camera selected in the list.")
            return {'CANCELLED'}

        return {'FINISHED'}

class MoveCameraUpOperator(Operator):
    bl_idname = "morph_list.move_camera_up"
    bl_label = "Move Camera Up"
    bl_description = "Moves the selected camera up in the morph list"

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'CAMERA' and obj.get("is_morph_camera") and obj.morph_props.active_morph_camera_index > 0

    def execute(self, context):
        morph_cam_obj = context.object
        morph_props = morph_cam_obj.morph_props
        index = morph_props.active_morph_camera_index
        morph_props.morph_list.move(index, index - 1)
        morph_props.active_morph_camera_index -= 1
        # Trigger immediate update if possible
        if context.scene.camera == morph_cam_obj:
            trigger_morph_update(context.scene, morph_cam_obj)
        return {'FINISHED'}

class MoveCameraDownOperator(Operator):
    bl_idname = "morph_list.move_camera_down"
    bl_label = "Move Camera Down"
    bl_description = "Moves the selected camera down in the morph list"

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not (obj and obj.type == 'CAMERA' and obj.get("is_morph_camera")):
            return False
        index = obj.morph_props.active_morph_camera_index
        return index < len(obj.morph_props.morph_list) - 1

    def execute(self, context):
        morph_cam_obj = context.object
        morph_props = morph_cam_obj.morph_props
        index = morph_props.active_morph_camera_index
        morph_props.morph_list.move(index, index + 1)
        morph_props.active_morph_camera_index += 1
        # Trigger immediate update if possible
        if context.scene.camera == morph_cam_obj:
            trigger_morph_update(context.scene, morph_cam_obj)
        return {'FINISHED'}

class BakeMorphCameraOperator(Operator):
    bl_idname = "morph_list.bake_morph_camera"
    bl_label = "Bake Morph Animation"
    bl_description = "Bakes the morph camera's animation to a new standard camera"

    @classmethod
    def poll(cls, context):
        obj = context.object
        # Ensure morph_props exists before checking list length
        return obj and obj.type == 'CAMERA' and obj.get("is_morph_camera") and hasattr(obj, 'morph_props') and len(obj.morph_props.morph_list) >= 2


    def execute(self, context):
        scene = context.scene
        morph_cam_obj = context.object # The camera with the morph properties
        morph_props = morph_cam_obj.morph_props # Assuming poll passed, this exists

        # Check again just in case poll context was odd (unlikely but safe)
        if len(morph_props.morph_list) < 2:
            self.report({'ERROR'}, "Need at least two cameras in the list to bake.")
            return {'CANCELLED'}

        # Create a new camera to bake the animation
        baked_camera_data = bpy.data.cameras.new(name=f"{morph_cam_obj.name}_BakedData")
        baked_camera_obj = bpy.data.objects.new(name=f"{morph_cam_obj.name}_Baked", object_data=baked_camera_data)
        scene.collection.objects.link(baked_camera_obj)

        # Store original frame (useful for restoring state after baking)
        original_frame = scene.frame_current
        # Store slider value too, mainly for restoring non-animated state accurately
        original_slider = scene.morph_slider if hasattr(scene, 'morph_slider') else 0.0

        frame_start = scene.frame_start
        frame_end = scene.frame_end

       
        print(f"Baking Morph Camera animation from frame {frame_start} to {frame_end}...") # Info

        # Bake the animation frame by frame
        for frame in range(frame_start, frame_end + 1):
            # Set the current frame. This automatically updates scene.morph_slider if it's keyframed.
            scene.frame_set(frame)
            # print(f"  Baking frame {frame}, Slider value: {scene.morph_slider:.3f}") # Debug Frame/Slider

            # Ensure the morph camera is updated based on the slider value *at this frame*
            trigger_morph_update(scene, morph_cam_obj)

            # Copy properties from the *current state* of the morph camera to the baked camera
            baked_camera_obj.location = morph_cam_obj.location
            # Ensure consistent rotation order if needed (e.g., 'XYZ')
            baked_camera_obj.rotation_euler = morph_cam_obj.rotation_euler
            baked_camera_data.lens = morph_cam_obj.data.lens

            # --- Copy other relevant properties ---
            # Example: Depth of Field
            baked_camera_data.dof.use_dof = morph_cam_obj.data.dof.use_dof
            baked_camera_data.dof.focus_distance = morph_cam_obj.data.dof.focus_distance
            baked_camera_data.dof.aperture_fstop = morph_cam_obj.data.dof.aperture_fstop
            # Example: Clipping
            baked_camera_data.clip_start = morph_cam_obj.data.clip_start
            baked_camera_data.clip_end = morph_cam_obj.data.clip_end
            # Example: Sensor Fit/Size (Important if source cameras differ)
            baked_camera_data.sensor_fit = morph_cam_obj.data.sensor_fit
            baked_camera_data.sensor_width = morph_cam_obj.data.sensor_width
            baked_camera_data.sensor_height = morph_cam_obj.data.sensor_height
            # ... copy any other properties you interpolated in update_morph_camera ...


            # --- Insert Keyframes for the baked camera ---
            baked_camera_obj.keyframe_insert(data_path="location", frame=frame)
            baked_camera_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
            baked_camera_data.keyframe_insert(data_path="lens", frame=frame)

            # Keyframe other copied properties
            baked_camera_data.dof.keyframe_insert(data_path="focus_distance", frame=frame)
            baked_camera_data.dof.keyframe_insert(data_path="aperture_fstop", frame=frame)
            baked_camera_data.keyframe_insert(data_path="clip_start", frame=frame)
            baked_camera_data.keyframe_insert(data_path="clip_end", frame=frame)
            baked_camera_data.keyframe_insert(data_path="sensor_fit", frame=frame)
            baked_camera_data.keyframe_insert(data_path="sensor_width", frame=frame)
            baked_camera_data.keyframe_insert(data_path="sensor_height", frame=frame)
            # ... keyframe others ...


        # Restore original frame
        scene.frame_set(original_frame)
        # Restore slider value too, just in case frame_set didn't perfectly restore non-animated state
        if hasattr(scene, 'morph_slider'):
             scene.morph_slider = original_slider
        print(f"Baking complete. Restored frame to {original_frame} and slider to {original_slider:.3f}")


        # Make baked camera the active scene camera
        scene.camera = baked_camera_obj
        # Optionally select the baked camera
        context.view_layer.objects.active = baked_camera_obj
        baked_camera_obj.select_set(True)

        self.report({'INFO'}, f"Baked animation to '{baked_camera_obj.name}'.")
        return {'FINISHED'}

# --- Panels ---
class MORPHCAMERA_PT_CameraPropertiesPanel(Panel):
    bl_label = "Morph Camera Settings"
    bl_idname = "CAMERA_PT_morph_camera_props"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data' # Show in Camera Data tab

    @classmethod
    def poll(cls, context):
        obj = context.object
        # Check the custom property OR the property group flag
        return obj and obj.type == 'CAMERA' and (obj.get("is_morph_camera") or (hasattr(obj, "morph_props") and obj.morph_props.is_morph_camera))


    def draw(self, context):
        layout = self.layout
        obj = context.object
        scene = context.scene
        morph_props = obj.morph_props # Access the property group

        layout.label(text="Target Cameras:")
        layout.template_list(
            "MORPHCAMERA_UL_CameraList", "",
            morph_props, "morph_list", # Use property group data path
            morph_props, "active_morph_camera_index" # Use property group data path
        )

        row = layout.row(align=True)
        row.operator("morph_list.add_selected_cameras", text="Add Selected")
        row.operator("morph_list.add_camera", text="Add Slot")
        row.operator("morph_list.remove_camera", text="Remove")

        row = layout.row(align=True)
        row.operator("morph_list.move_camera_up", text="Up")
        row.operator("morph_list.move_camera_down", text="Down")

        layout.separator()

        # Slider controls
        if len(morph_props.morph_list) > 1:
            layout.prop(scene, "morph_slider", text="Morph", slider=True) # Scene property for slider
            layout.prop(morph_props, "arc_control", text="Arc Control", slider=True) # Object property for arc
        else:
            layout.label(text="Add at least two cameras to morph.")

        layout.separator()
        layout.operator("morph_list.bake_morph_camera", text="Bake Animation")


# Optional: View 3D Panel (can be removed if Properties panel is enough)
class MORPHCAMERA_PT_View3DPanel(Panel):
    bl_label = "Morph Camera"
    bl_idname = "VIEW3D_PT_morph_camera_ui"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Morph Cam' # Tab name in View 3D N-Panel

    @classmethod
    def poll(cls, context):
         # Only show if the *active* object is a morph camera
         # Or maybe show if *any* morph camera exists? Let's stick to active obj for simplicity.
        obj = context.object
        return obj and obj.type == 'CAMERA' and (obj.get("is_morph_camera") or (hasattr(obj, "morph_props") and obj.morph_props.is_morph_camera))


    def draw(self, context):
        # Reuse the drawing logic from the properties panel for consistency
        MORPHCAMERA_PT_CameraPropertiesPanel.draw(self, context)


# --- Property Group for Morph Camera ---
# We store morph-specific properties here, attached to the Object type
class MorphCameraProperties(PropertyGroup):
    is_morph_camera: bpy.props.BoolProperty(name="Is Morph Camera Flag", default=False, options={'HIDDEN'}) # Internal flag
    morph_list: CollectionProperty(type=MorphListItem)
    active_morph_camera_index: IntProperty(name="Active List Index", default=0)
    arc_control: FloatProperty(
        name="Arc Control",
        description="Control the arc of the morphing path (-1 to 1)",
        default=0.0, min=-1.0, max=1.0,
        subtype='FACTOR'
        )

# --- Core Logic ---

# Global flag to prevent recursive updates from depsgraph handler
_update_in_progress_flag = False

def get_evaluated_camera(cam_obj, depsgraph):
    """Safely get the evaluated camera object."""
    if not cam_obj:
        return None
    try:
        return cam_obj.evaluated_get(depsgraph)
    except Exception: # Handles cases where object might be invalid (e.g., deleted)
         print(f"Warning: Could not evaluate camera: {cam_obj.name}")
         return None

def get_focus_distance(camera_eval):
    """Get focus distance from evaluated camera, handling focus object."""
    if not camera_eval or not camera_eval.data:
        return 10.0 # Default value

    dof_data = camera_eval.data.dof
    if dof_data.use_dof and dof_data.focus_object:
        try:
            focus_obj_eval = dof_data.focus_object.evaluated_get(bpy.context.evaluated_depsgraph_get()) # Need current depsgraph
            if focus_obj_eval:
                return (camera_eval.matrix_world.translation - focus_obj_eval.matrix_world.translation).length
            else:
                return dof_data.focus_distance # Fallback if focus object not evaluatable
        except Exception:
             return dof_data.focus_distance # Fallback on error
    else:
        return dof_data.focus_distance

def interpolate_bezier(p0, p1, p2, t):
    """Quadratic Bezier interpolation."""
    omt = 1.0 - t
    return omt**2 * p0 + 2.0 * omt * t * p1 + t**2 * p2

def update_morph_camera(scene, morph_cam_obj, depsgraph):
    """
    Updates the transform and properties of the morph_cam_obj based on the morph_list and slider.
    Now takes the morph_cam_obj and depsgraph directly, avoiding context issues.
    """
    global _update_in_progress_flag
    if _update_in_progress_flag:
        # print("Update already in progress, skipping.")
        return
    if not morph_cam_obj or not hasattr(morph_cam_obj, 'morph_props'):
        # print("Invalid morph camera object passed.")
        return

    _update_in_progress_flag = True # Set flag

    try:
        morph_props = morph_cam_obj.morph_props
        morph_list = morph_props.morph_list
        slider_value = scene.morph_slider
        num_cams = len(morph_list)

        # print(f"Updating Morph Cam '{morph_cam_obj.name}': Slider={slider_value:.2f}, Cams={num_cams}") # Debug

        if num_cams < 2:
            # print("Not enough cameras in list.")
            _update_in_progress_flag = False
            return # Need at least two cameras

        # Clamp slider value to valid range (though slider definition should handle this)
        slider_value = max(0.0, min(slider_value, num_cams - 1.0))

        # Determine which two cameras to interpolate between
        idx_float = slider_value
        idx0 = int(idx_float)
        idx1 = min(idx0 + 1, num_cams - 1) # Ensure idx1 doesn't go out of bounds

        # Get the interpolation factor (t) between cam0 and cam1
        t = idx_float - idx0

        # Get the actual camera objects from the list
        item0 = morph_list[idx0] if idx0 < len(morph_list) else None
        item1 = morph_list[idx1] if idx1 < len(morph_list) else None

        cam0_orig = item0.camera if item0 else None
        cam1_orig = item1.camera if item1 else None

        # Get evaluated versions for accurate world space data
        cam0 = get_evaluated_camera(cam0_orig, depsgraph)
        cam1 = get_evaluated_camera(cam1_orig, depsgraph)

        if not cam0 or not cam1:
             # print(f"Warning: Missing evaluated camera for interpolation. Cam0: {cam0}, Cam1: {cam1}")
             _update_in_progress_flag = False
             if cam0 and not cam1: # If only cam0 exists, snap to it
                 morph_cam_obj.location = cam0.matrix_world.translation
                 morph_cam_obj.rotation_euler = cam0.matrix_world.to_euler('XYZ') # Use consistent order
                 morph_cam_obj.data.lens = cam0.data.lens
             elif cam1 and not cam0: # If only cam1 exists, snap to it
                 morph_cam_obj.location = cam1.matrix_world.translation
                 morph_cam_obj.rotation_euler = cam1.matrix_world.to_euler('XYZ')
                 morph_cam_obj.data.lens = cam1.data.lens
             # else: both missing, do nothing
             return

        # --- Interpolation ---
        loc0 = cam0.matrix_world.translation
        loc1 = cam1.matrix_world.translation

        # Rotation (use Slerp for better interpolation)
        quat0 = cam0.matrix_world.to_quaternion()
        quat1 = cam1.matrix_world.to_quaternion()
        interp_quat = quat0.slerp(quat1, t)

        # Lens and DOF
        lens0 = cam0.data.lens
        lens1 = cam1.data.lens
        focus0 = get_focus_distance(cam0)
        focus1 = get_focus_distance(cam1)
        fstop0 = cam0.data.dof.aperture_fstop
        fstop1 = cam1.data.dof.aperture_fstop
        # Add other properties here...

        # Arc Control for Location
        if morph_props.arc_control != 0.0 and loc0 != loc1:
            mid_point = (loc0 + loc1) / 2.0
            # Vector from start to end
            vec = loc1 - loc0
            # Need a consistent "up" vector - try world Z, fallback to Y if vec is aligned with Z
            up_vec = Vector((0.0, 0.0, 1.0))
            if vec.normalized().dot(up_vec) > 0.999 or vec.normalized().dot(up_vec) < -0.999:
                up_vec = Vector((0.0, 1.0, 0.0))
            # Perpendicular vector in the plane defined by vec and up_vec
            perp_vec = vec.cross(up_vec).normalized()
             # Arc offset strength depends on t (max at t=0.5) and arc_control
            arc_strength = morph_props.arc_control * vec.length * 0.5 * (1.0 - abs(2.0 * t - 1.0)) # Scale arc by distance
            arc_offset = perp_vec * arc_strength
            # Control point for Bezier curve
            control_point = mid_point + arc_offset
            interp_loc = interpolate_bezier(loc0, control_point, loc1, t)
        else:
            # Linear interpolation if no arc or start/end points are same
            interp_loc = loc0.lerp(loc1, t)


        # --- Apply interpolated values to the Morph Camera ---
        morph_cam_obj.location = interp_loc
        morph_cam_obj.rotation_euler = interp_quat.to_euler('XYZ') # Use consistent order

        morph_cam_obj.data.lens = lens0 * (1.0 - t) + lens1 * t
        morph_cam_obj.data.dof.focus_distance = focus0 * (1.0 - t) + focus1 * t
        morph_cam_obj.data.dof.aperture_fstop = fstop0 * (1.0 - t) + fstop1 * t

        # Update DOF enabled state (enable if either source cam has it enabled)
        morph_cam_obj.data.dof.use_dof = cam0.data.dof.use_dof or cam1.data.dof.use_dof

        # Interpolate other camera settings if desired (clip start/end, sensor size etc.)
        # morph_cam_obj.data.clip_start = cam0.data.clip_start * (1.0 - t) + cam1.data.clip_start * t
        # morph_cam_obj.data.clip_end = cam0.data.clip_end * (1.0 - t) + cam1.data.clip_end * t


    except Exception as e:
        print(f"Error in update_morph_camera: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging
    finally:
         _update_in_progress_flag = False # Release flag


# --- Update Triggers ---

def find_morph_camera(scene):
    """Utility to find the first morph camera in the scene."""
    for obj in scene.objects:
        # Check both the custom prop (legacy) and the property group flag
        if obj.type == 'CAMERA' and (obj.get("is_morph_camera") or (hasattr(obj, "morph_props") and obj.morph_props.is_morph_camera)):
            return obj
    return None

def trigger_morph_update(scene, morph_cam_obj=None):
    """Finds the morph camera (if not provided) and calls the update function."""
    if not morph_cam_obj:
        morph_cam_obj = find_morph_camera(scene)

    if morph_cam_obj:
        depsgraph = bpy.context.evaluated_depsgraph_get() # Get current depsgraph
        update_morph_camera(scene, morph_cam_obj, depsgraph)
    # else:
        # print("Trigger Morph Update: No Morph Camera found.")



# Callback function for the morph_slider Scene property
# Needs to be defined *before* register_morph_slider uses it
def morph_slider_update_callback(self, context):
    """Callback when scene.morph_slider changes."""
    # print(f"Slider updated to: {self.morph_slider}") # Debug
    trigger_morph_update(self) # Pass the scene


# !! NEW Function to define/redefine the Scene property !!
def register_morph_slider(max_val):
    """
    Defines or redefines the Scene.morph_slider property.
    This function should be called whenever the range needs to change.
    """
    # Ensure max_val is at least 0 for UI sanity, even if list has < 2 items.
    # The update logic should handle non-morphing states separately anyway.
    safe_max = max(0.0, float(max_val)) # Ensure it's float

    # Check if property exists before trying to delete (optional safety)
    if hasattr(bpy.types.Scene, 'morph_slider'):
         print(f"Deleting existing morph_slider definition before re-registering.")
         try:
             # Must delete from the TYPE, not the instance
             del bpy.types.Scene.morph_slider
         except Exception as e:
              print(f"Warning: Could not delete previous morph_slider: {e}")


    print(f"Registering Scene.morph_slider with max={safe_max}") # DEBUG
    bpy.types.Scene.morph_slider = FloatProperty(
        name="Morph Slider",
        description="Morph between listed cameras (0=first, 1=second, etc.)",
        default=0.0,
        min=0.0,
        max=safe_max, # Use the calculated max here
        soft_min=0.0,
        soft_max=safe_max, # Set soft_max too
        precision=3,
        step=0.01,
        # subtype='FACTOR', # Ensure subtype is NOT used
        update=morph_slider_update_callback # Assign the update callback
    )


# !! MODIFIED update_slider_range function !!
def update_slider_range(scene):
    """Updates the max value of the morph_slider by potentially redefining the property."""
    print("Running update_slider_range (redefine method)...") # DEBUG
    morph_cam_obj = find_morph_camera(scene)
    target_max_val = 0.0 # Default max if no morph or < 2 cameras
    num_cams = 0
    if morph_cam_obj and hasattr(morph_cam_obj, 'morph_props'):
        num_cams = len(morph_cam_obj.morph_props.morph_list)
        if num_cams > 1:
            target_max_val = float(num_cams - 1)
    print(f"  Target max value based on {num_cams} cameras: {target_max_val}") # DEBUG

    current_max = -1.0 # Flag value indicates not found or error
    needs_redefine = True # Assume we need to redefine unless proven otherwise

    # Check if property exists and read its *current* hard_max
    if hasattr(bpy.types.Scene, 'morph_slider'):
        try:
            rna_prop = bpy.types.Scene.bl_rna.properties.get('morph_slider')
            if rna_prop:
                # We *can* read hard_max
                current_max = rna_prop.hard_max
                print(f"  Current slider hard_max found: {current_max}") # DEBUG
                # Compare floats with a small tolerance
                if abs(current_max - target_max_val) < 0.001:
                    needs_redefine = False
                    print("  Slider range already correct.") # DEBUG
            else:
                print("  Warning: morph_slider exists but couldn't get RNA property.") # DEBUG
        except Exception as e:
            print(f"  Warning: Error reading current slider max: {e}") # DEBUG
    else:
        print("  morph_slider property does not currently exist.") # DEBUG


    if needs_redefine:
        print(f"  Slider range needs update/creation (Target: {target_max_val}). Redefining property.") # DEBUG
        current_value = 0.0
        # Store current value *before* deleting/redefining property, if it exists on the scene instance
        if hasattr(scene, 'morph_slider'):
             try:
                 current_value = scene.morph_slider
                 print(f"  Stored current slider value: {current_value}") # DEBUG
             except Exception as e:
                  print(f"  Warning: Could not read current scene.morph_slider value: {e}")


        # --- Redefine the property ---
        # The helper function now handles deletion internally before re-adding
        register_morph_slider(target_max_val)
        # --- Property is now redefined ---


        # Restore the value to the scene instance, clamping if necessary
        try:
             # Clamp between 0.0 and the new target max
             clamped_value = max(0.0, min(current_value, target_max_val))
             # Assign to the scene instance property
             scene.morph_slider = clamped_value
             print(f"  Restored slider value to: {clamped_value}") # DEBUG
        except Exception as e:
             print(f"  Error restoring slider value: {e}") # DEBUG

    # If no redefine was needed, still ensure current value is clamped (e.g., if user manually typed > max)
    elif hasattr(scene, 'morph_slider'):
         if scene.morph_slider > current_max or scene.morph_slider < 0.0:
              clamped_value = max(0.0, min(scene.morph_slider, current_max))
              print(f"Clamping existing slider value {scene.morph_slider} to range [0, {current_max}]. New value: {clamped_value}")
              scene.morph_slider = clamped_value


# --- Application Handlers ---

# Use functools.partial to create persistent references for handlers
# This helps prevent issues with handlers being garbage collected unexpectedly
@bpy.app.handlers.persistent
def morph_frame_change_handler(scene, depsgraph=None):
    """Handler for frame changes (pre or post)."""
    # print(f"Frame Change Handler: Frame {scene.frame_current}") # Debug
    # The depsgraph is sometimes passed on frame change post, sometimes not.
    # It's more reliable to get it inside trigger_morph_update if needed.
    trigger_morph_update(scene)

@bpy.app.handlers.persistent
def morph_depsgraph_update_handler(scene, depsgraph):
    """Handler for dependency graph updates (post)."""
    # This runs VERY often. Use with caution.
    # Useful if source cameras are animated or constrained.
    # print("Depsgraph Handler Triggered") # Debug - Warning: Very frequent!
    trigger_morph_update(scene) # Depsgraph already available

@bpy.app.handlers.persistent
def morph_load_post_handler(dummy):
    """Handler run once after a .blend file is loaded."""
    print("Morph Cam Addon: Load Post Handler Running...")
    scene = bpy.context.scene
    if not scene:
        print("Load Handler: No scene context.")
        return

    # Need to re-evaluate the slider range after load
    update_slider_range(scene)

    # Trigger an initial update for the morph camera based on loaded slider value
    trigger_morph_update(scene)
    print("Morph Cam Addon: Initial update triggered after load.")


# List to keep track of registered handlers for easy removal
_registered_handlers = []

# --- Registration ---
classes = (
    MorphListItem,
    MORPHCAMERA_UL_CameraList,
    MorphCameraProperties, # Register the PropertyGroup itself
    AddMorphCameraOperator,
    AddSelectedCamerasToListOperator,
    AddCameraToListOperator,
    RemoveCameraFromListOperator,
    MoveCameraUpOperator,
    MoveCameraDownOperator,
    BakeMorphCameraOperator,
    MORPHCAMERA_PT_CameraPropertiesPanel,
    MORPHCAMERA_PT_View3DPanel,
)

def register():
    print("Registering Morph Camera Addon (Fixed)...")
    for cls in classes:
        bpy.utils.register_class(cls)

    # Assign the PropertyGroup to the Object type
    bpy.types.Object.morph_props = PointerProperty(type=MorphCameraProperties)

    # Perform initial registration of the slider property
    # Use a sensible default, like 1.0 (for 2 cameras) or 0.0 if preferred when no list exists yet
    register_morph_slider(1.0)


    # Register handlers
    # Frame change post often works well as constraints/drivers have evaluated
    handlers_to_register = [
        (bpy.app.handlers.frame_change_post, morph_frame_change_handler),
        # (bpy.app.handlers.depsgraph_update_post, morph_depsgraph_update_handler), # Uncomment if needed, but performance heavy
        (bpy.app.handlers.load_post, morph_load_post_handler),
    ]

    global _registered_handlers
    _registered_handlers.clear() # Clear previous list if re-registering

    for handler_list, handler_func in handlers_to_register:
        if handler_func not in handler_list:
            handler_list.append(handler_func)
            _registered_handlers.append((handler_list, handler_func)) # Store for unregister
            # print(f"Registered handler: {handler_func.__name__}") # Debug

    # Add button to Add > Camera menu
    bpy.types.VIEW3D_MT_camera_add.append(add_morph_camera_button_draw)

    print(f"Morph Camera Addon Registered. Handlers: {_registered_handlers}")

def unregister():
    print("Unregistering Morph Camera Addon (Fixed - Redefine Slider)...")

    global _registered_handlers
    # Remove handlers safely
    for handler_list, handler_func in _registered_handlers:
        if handler_func in handler_list:
            try:
                handler_list.remove(handler_func)
            except Exception as e:
                 print(f"Error removing handler {handler_func.__name__}: {e}")
    _registered_handlers.clear()


    # Remove button from menu
    try:
        bpy.types.VIEW3D_MT_camera_add.remove(add_morph_camera_button_draw)
    except Exception as e:
         print(f"Error removing menu item: {e}")


    # Delete the scene property definition IF it exists
    if hasattr(bpy.types.Scene, 'morph_slider'):
        try:
            del bpy.types.Scene.morph_slider
            print("Unregistered morph_slider property definition.") # DEBUG
        except Exception as e:
             print(f"Error deleting morph_slider property definition during unregister: {e}")


    # Delete the property group pointer from Object type
    # Use try-except as it might fail if registration itself failed partially
    try:
        if hasattr(bpy.types.Object, 'morph_props'):
             del bpy.types.Object.morph_props
    except Exception as e:
         print(f"Error deleting Object.morph_props during unregister: {e}")


    # Unregister classes in reverse order
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
             print(f"Error unregistering class {cls.__name__}: {e}")


    print("Morph Camera Addon Unregistered.")


# --- Menu item drawing function ---
def add_morph_camera_button_draw(self, context):
    self.layout.operator(AddMorphCameraOperator.bl_idname, icon='CAMERA_DATA')

# --- Main Guard ---
if __name__ == "__main__":
    # Example for testing in Blender's text editor
    try: unregister()
    except: pass
    register()
