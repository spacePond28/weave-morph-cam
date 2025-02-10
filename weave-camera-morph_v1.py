bl_info = {
    "name": "Weave Camera Morph V1",
    "blender": (2, 80, 0),
    "category": "Object",
}

import bpy
from bpy.props import PointerProperty, CollectionProperty, FloatProperty, IntProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList
from mathutils import Vector

class AddMorphCameraOperator(bpy.types.Operator):
    bl_idname = "object.add_morph_camera"
    bl_label = "Add Morph Camera"
    
    def execute(self, context):
        scene = context.scene
        loc = scene.cursor.location
        rot = (0.0, 0.0, 0.0)
        
        morph_camera = bpy.data.cameras.new(name="MorphCamera")
        morph_camera_obj = bpy.data.objects.new(name="MorphCamera", object_data=morph_camera)
        morph_camera_obj.location = loc
        morph_camera_obj.rotation_euler = rot
        morph_camera_obj["is_morph_camera"] = True  # Add custom property to identify Morph Camera
        scene.collection.objects.link(morph_camera_obj)
        scene.camera = morph_camera_obj
        
        return {'FINISHED'}

class MorphListItem(PropertyGroup):
    camera: PointerProperty(name="Camera", type=bpy.types.Object)

class MORPHCAMERA_UL_CameraList(UIList):
    bl_idname = "MORPHCAMERA_UL_CameraList"
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "camera", text="", icon='CAMERA_DATA')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.prop(item, "camera", text="", icon='CAMERA_DATA')

class AddSelectedCamerasToListOperator(bpy.types.Operator):
    bl_idname = "morph_list.add_selected_cameras"
    bl_label = "Add Selected Cameras to Morph List"
    
    def execute(self, context):
        obj = context.object
        
        if obj and obj.type == 'CAMERA' and "is_morph_camera" in obj:
            selected_cameras = [cam for cam in bpy.context.selected_objects if cam.type == 'CAMERA' and cam != obj]
            for selected_camera in selected_cameras:
                item = obj.morph_list.add()
                item.camera = selected_camera
            update_slider_range(context.scene)
            update_morph_camera(context.scene, context)
            
        return {'FINISHED'}

class AddCameraToListOperator(bpy.types.Operator):
    bl_idname = "morph_list.add_camera"
    bl_label = "Add Camera to Morph List"
    
    def execute(self, context):
        obj = context.object
        
        if obj and obj.type == 'CAMERA' and "is_morph_camera" in obj:
            item = obj.morph_list.add()
            item.camera = None  # Add an empty item for the user to set manually
            update_slider_range(context.scene)
            update_morph_camera(context.scene, context)
            
        return {'FINISHED'}

class RemoveCameraFromListOperator(bpy.types.Operator):
    bl_idname = "morph_list.remove_camera"
    bl_label = "Remove Camera from Morph List"
    
    def execute(self, context):
        obj = context.object
        
        if obj and obj.type == 'CAMERA' and "is_morph_camera" in obj:
            if obj.morph_list:
                obj.morph_list.remove(obj.active_morph_camera_index)
                obj.active_morph_camera_index = max(0, obj.active_morph_camera_index - 1)
                update_slider_range(context.scene)
                update_morph_camera(context.scene, context)
        
        return {'FINISHED'}

class MoveCameraUpOperator(bpy.types.Operator):
    bl_idname = "morph_list.move_camera_up"
    bl_label = "Move Camera Up"
    
    def execute(self, context):
        obj = context.object
        index = obj.active_morph_camera_index
        
        if obj and obj.type == 'CAMERA' and "is_morph_camera" in obj and index > 0:
            obj.morph_list.move(index, index - 1)
            obj.active_morph_camera_index -= 1
            update_slider_range(context.scene)
            update_morph_camera(context.scene, context)
        
        return {'FINISHED'}

class MoveCameraDownOperator(bpy.types.Operator):
    bl_idname = "morph_list.move_camera_down"
    bl_label = "Move Camera Down"
    
    def execute(self, context):
        obj = context.object
        index = obj.active_morph_camera_index
        
        if obj and obj.type == 'CAMERA' and "is_morph_camera" in obj and index < len(obj.morph_list) - 1:
            obj.morph_list.move(index, index + 1)
            obj.active_morph_camera_index += 1
            update_slider_range(context.scene)
            update_morph_camera(context.scene, context)
        
        return {'FINISHED'}

class UpdateMorphCameraOperator(bpy.types.Operator):
    bl_idname = "morph_list.update_morph_camera"
    bl_label = "Update Morph Camera"
    
    def execute(self, context):
        update_morph_camera(context.scene, context)
        return {'FINISHED'}

class BakeMorphCameraOperator(bpy.types.Operator):
    bl_idname = "morph_list.bake_morph_camera"
    bl_label = "Bake Morph Camera"
    
    def execute(self, context):
        scene = context.scene
        obj = context.object
        
        if obj and obj.type == 'CAMERA' and "is_morph_camera" in obj:
            # Create a new camera to bake the animation
            baked_camera = bpy.data.cameras.new(name="BakedMorphCamera")
            baked_camera_obj = bpy.data.objects.new(name="BakedMorphCamera", object_data=baked_camera)
            scene.collection.objects.link(baked_camera_obj)
            
            # Bake the animation
            frame_start = scene.frame_start
            frame_end = scene.frame_end
            
            for frame in range(frame_start, frame_end + 1):
                scene.frame_set(frame)
                update_morph_camera(scene, context)
                
                baked_camera_obj.location = obj.location
                baked_camera_obj.rotation_euler = obj.rotation_euler
                baked_camera_obj.data.lens = obj.data.lens
                baked_camera_obj.data.dof.focus_distance = obj.data.dof.focus_distance
                baked_camera_obj.data.dof.aperture_blades = obj.data.dof.aperture_blades
                baked_camera_obj.data.dof.aperture_fstop = obj.data.dof.aperture_fstop
                baked_camera_obj.data.dof.aperture_ratio = obj.data.dof.aperture_ratio
                baked_camera_obj.data.dof.aperture_rotation = obj.data.dof.aperture_rotation
                
                baked_camera_obj.keyframe_insert(data_path="location", frame=frame)
                baked_camera_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
                baked_camera_obj.data.keyframe_insert(data_path="lens", frame=frame)
                baked_camera_obj.data.dof.keyframe_insert(data_path="focus_distance", frame=frame)
                baked_camera_obj.data.dof.keyframe_insert(data_path="aperture_blades", frame=frame)
                baked_camera_obj.data.dof.keyframe_insert(data_path="aperture_fstop", frame=frame)
                baked_camera_obj.data.dof.keyframe_insert(data_path="aperture_ratio", frame=frame)
                baked_camera_obj.data.dof.keyframe_insert(data_path="aperture_rotation", frame=frame)
            
            scene.camera = baked_camera_obj
        
        return {'FINISHED'}

class MorphCameraPanel(Panel):
    bl_label = "Morph Camera Settings"
    bl_idname = "CAMERA_PT_morph_camera"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'
    
    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'CAMERA' and "is_morph_camera" in obj
    
    def draw(self, context):
        layout = self.layout
        obj = context.object
        
        layout.label(text="Camera Morph List")
        layout.template_list("MORPHCAMERA_UL_CameraList", "", obj, "morph_list", obj, "active_morph_camera_index")
        
        row = layout.row(align=True)
        row.operator("morph_list.move_camera_up", text="Up")
        row.operator("morph_list.move_camera_down", text="Down")
        
        layout.operator("morph_list.add_selected_cameras", text="Add Selected Cameras")
        layout.operator("morph_list.add_camera", text="Add Camera Manually")
        layout.operator("morph_list.remove_camera", text="Remove Camera")
        layout.operator("morph_list.update_morph_camera", text="Update Morph Camera")
        layout.operator("morph_list.bake_morph_camera", text="Bake Morph Camera")
        
        # Update the slider range dynamically
        if len(obj.morph_list) > 1:
            layout.prop(context.scene, "morph_slider", text="Morph Slider", slider=True)
            layout.prop(obj, "arc_control", text="Arc Control", slider=True)
        else:
            layout.label(text="Add at least two cameras to use the morph slider.")

class MorphCameraViewportPanel(Panel):
    bl_label = "Morph Camera"
    bl_idname = "VIEW3D_PT_morph_camera"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Morph Camera'
    
    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'CAMERA' and "is_morph_camera" in obj
    
    def draw(self, context):
        layout = self.layout
        obj = context.object
        
        layout.label(text="Camera Morph List")
        layout.template_list("MORPHCAMERA_UL_CameraList", "", obj, "morph_list", obj, "active_morph_camera_index")
        
        row = layout.row(align=True)
        row.operator("morph_list.move_camera_up", text="Up")
        row.operator("morph_list.move_camera_down", text="Down")
        
        layout.operator("morph_list.add_selected_cameras", text="Add Selected Cameras")
        layout.operator("morph_list.add_camera", text="Add Camera Manually")
        layout.operator("morph_list.remove_camera", text="Remove Camera")
        layout.operator("morph_list.update_morph_camera", text="Update Morph Camera")
        layout.operator("morph_list.bake_morph_camera", text="Bake Morph Camera")
        
        # Update the slider range dynamically
        if len(obj.morph_list) > 1:
            layout.prop(context.scene, "morph_slider", text="Morph Slider", slider=True)
            layout.prop(obj, "arc_control", text="Arc Control", slider=True)
        else:
            layout.label(text="Add at least two cameras to use the morph slider.")

class MorphCameraProperties(PropertyGroup):
    morph_list: CollectionProperty(type=MorphListItem)
    active_morph_camera_index: IntProperty()
    arc_control: FloatProperty(
        name="Arc Control",
        description="Control the arc of the morphing path",
        default=0.0,
        min=-1.0,
        max=1.0
    )

def get_focus_distance(camera):
    if camera.data.dof.focus_object:
        return (camera.matrix_world.translation - camera.data.dof.focus_object.matrix_world.translation).length
    else:
        return camera.data.dof.focus_distance

def interpolate_bezier(p0, p1, p2, t):
    return (1 - t)**2 * p0 + 2 * (1 - t) * t * p1 + t**2 * p2

def update_morph_camera(scene, context):
    obj = context.object
    if obj and obj.type == 'CAMERA' and "is_morph_camera" in obj:
        morph_list = obj.morph_list
        if len(morph_list) < 2:
            return
        
        slider_value = context.scene.morph_slider
        total_cameras = len(morph_list)
        
        depsgraph = context.evaluated_depsgraph_get()
        
        for i in range(total_cameras - 1):
            if slider_value >= i and slider_value <= i + 1:
                t = slider_value - i
                cam1 = morph_list[i].camera.evaluated_get(depsgraph)
                cam2 = morph_list[i + 1].camera.evaluated_get(depsgraph)
                
                if cam1 and cam2:
                    # Calculate the arc position using Bezier interpolation
                    p0 = cam1.matrix_world.translation
                    p2 = cam2.matrix_world.translation
                    mid_point = (p0 + p2) / 2
                    arc_offset = (p0 - p2).cross(Vector((0, 0, 1))).normalized() * context.object.arc_control * (1 - abs(2 * t - 1))
                    p1 = mid_point + arc_offset
                    
                    obj.location = interpolate_bezier(p0, p1, p2, t)
                    
                    # Use world matrix to get the correct rotation
                    rot1 = cam1.matrix_world.to_euler()
                    rot2 = cam2.matrix_world.to_euler()
                    obj.rotation_euler = rot1.to_quaternion().slerp(rot2.to_quaternion(), t).to_euler()
                    
                    obj.data.lens = cam1.data.lens * (1 - t) + cam2.data.lens * t
                    
                    # Morph additional camera attributes
                    focus_distance1 = get_focus_distance(cam1)
                    focus_distance2 = get_focus_distance(cam2)
                    obj.data.dof.focus_distance = focus_distance1 * (1 - t) + focus_distance2 * t
                    obj.data.dof.aperture_blades = int(cam1.data.dof.aperture_blades * (1 - t) + cam2.data.dof.aperture_blades * t)
                    obj.data.dof.aperture_fstop = cam1.data.dof.aperture_fstop * (1 - t) + cam2.data.dof.aperture_fstop * t
                    obj.data.dof.aperture_ratio = cam1.data.dof.aperture_ratio * (1 - t) + cam2.data.dof.aperture_ratio * t
                    obj.data.dof.aperture_rotation = cam1.data.dof.aperture_rotation * (1 - t) + cam2.data.dof.aperture_rotation * t
                    
                    # Ensure DOF settings are applied correctly
                    obj.data.dof.use_dof = cam1.data.dof.use_dof or cam2.data.dof.use_dof
                    
                break
            
def update_slider_range(scene):
    obj = bpy.context.object
    if obj and obj.type == 'CAMERA' and "is_morph_camera" in obj:
        total_cameras = len(obj.morph_list)
        if total_cameras > 1:
            scene.morph_slider = min(scene.morph_slider, total_cameras - 1)
            bpy.types.Scene.morph_slider = FloatProperty(
                name="Morph Slider",
                description="Morph between selected cameras",
                default=0.0,
                min=0.0,
                max=total_cameras - 1,
                update=update_morph_camera
            )

def frame_change_handler(scene):
    update_morph_camera(scene, bpy.context)

def draw_morph_camera_button(self, context):
    self.layout.operator(AddMorphCameraOperator.bl_idname, text="Add Morph Camera", icon='CAMERA_DATA')

def register():
    bpy.utils.register_class(AddMorphCameraOperator)
    bpy.utils.register_class(MorphListItem)
    bpy.utils.register_class(MORPHCAMERA_UL_CameraList)
    bpy.utils.register_class(AddSelectedCamerasToListOperator)
    bpy.utils.register_class(AddCameraToListOperator)
    bpy.utils.register_class(RemoveCameraFromListOperator)
    bpy.utils.register_class(MoveCameraUpOperator)
    bpy.utils.register_class(MoveCameraDownOperator)
    bpy.utils.register_class(UpdateMorphCameraOperator)
    bpy.utils.register_class(BakeMorphCameraOperator)
    bpy.utils.register_class(MorphCameraPanel)
    bpy.utils.register_class(MorphCameraViewportPanel)
    bpy.utils.register_class(MorphCameraProperties)
    
    bpy.types.Object.morph_list = CollectionProperty(type=MorphListItem)
    bpy.types.Object.active_morph_camera_index = IntProperty()
    bpy.types.Object.arc_control = FloatProperty(
        name="Arc Control",
        description="Control the arc of the morphing path",
        default=0.0,
        min=-1.0,
        max=1.0
    )
    bpy.types.Scene.morph_slider = FloatProperty(
        name="Morph Slider",
        description="Morph between selected cameras",
        default=0.0,
        min=0.0,
        max=1.0,
        update=update_morph_camera
    )

    bpy.app.handlers.frame_change_post.append(frame_change_handler)
    bpy.types.VIEW3D_MT_camera_add.append(draw_morph_camera_button)

def unregister():
    bpy.utils.unregister_class(AddMorphCameraOperator)
    bpy.utils.unregister_class(MorphListItem)
    bpy.utils.unregister_class(MORPHCAMERA_UL_CameraList)
    bpy.utils.unregister_class(AddSelectedCamerasToListOperator)
    bpy.utils.unregister_class(AddCameraToListOperator)
    bpy.utils.unregister_class(RemoveCameraFromListOperator)
    bpy.utils.unregister_class(MoveCameraUpOperator)
    bpy.utils.unregister_class(MoveCameraDownOperator)
    bpy.utils.unregister_class(UpdateMorphCameraOperator)
    bpy.utils.unregister_class(BakeMorphCameraOperator)
    bpy.utils.unregister_class(MorphCameraPanel)
    bpy.utils.unregister_class(MorphCameraViewportPanel)
    bpy.utils.unregister_class(MorphCameraProperties)
    
    del bpy.types.Object.morph_list
    del bpy.types.Object.active_morph_camera_index
    del bpy.types.Object.arc_control
    del bpy.types.Scene.morph_slider
    
    bpy.app.handlers.frame_change_post.remove(frame_change_handler)
    bpy.types.VIEW3D_MT_camera_add.remove(draw_morph_camera_button)

if __name__ == "__main__":
    register()