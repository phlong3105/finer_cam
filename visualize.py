import os
import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm
import argparse
from class_names import class_names_car

def normalize_label(label):
    return ''.join(filter(str.isalnum, label.lower()))

def extract_core_name_from_image_path(img_path):
    dir_name = os.path.dirname(img_path)
    class_name = os.path.basename(dir_name)
    file_name = os.path.basename(img_path)
    index = os.path.splitext(file_name)[0]
    core_name = f"{class_name}_{index}"
    return core_name

def load_and_preprocess_image(img_path):
    image = Image.open(img_path).convert('RGB')
    image = image.resize((224, 224)) 
    image = np.array(image).astype(np.float32) / 255.0
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image

def visualize_cam_on_image(image_bgr, cam):
    cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
    cam = np.squeeze(cam)
    image_resized = cv2.resize(image_bgr, (224, 224))
    image_rgb = cv2.cvtColor(image_resized, cv2.COLOR_BGR2RGB)
    image_rgb = (image_rgb * 255).astype(np.uint8)
    heatmap_bgr = cv2.applyColorMap(np.uint8(255 * cam), cv2.COLORMAP_JET)
    heatmap_rgb = cv2.cvtColor(heatmap_bgr, cv2.COLOR_BGR2RGB)
    visualization_rgb = cv2.addWeighted(image_rgb, 0.5, heatmap_rgb, 0.5, 0)
    visualization_bgr = cv2.cvtColor(visualization_rgb, cv2.COLOR_RGB2BGR)
    return visualization_bgr

def get_image_paths_from_folder(folder_path):
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp')
    image_paths = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(image_extensions):
                image_paths.append(os.path.join(root, file))
    return image_paths

def main(args):
    os.makedirs(args.save_dir, exist_ok=True)
    image_paths = get_image_paths_from_folder(args.dataset_dir)

    class_to_image_paths = {}
    for path in image_paths:
        class_name = os.path.basename(os.path.dirname(path))
        normalized_class_name = normalize_label(class_name)
        class_to_image_paths.setdefault(normalized_class_name, []).append(path)

    for img_path in tqdm(image_paths, desc="Processing images"):
        core_name = extract_core_name_from_image_path(img_path)
        original_image = load_and_preprocess_image(img_path)


        vis_list = []
        labels = []
        vis_list.append((original_image * 255).astype(np.uint8))
        labels.append('Original Image')

        gradcam_cam_path = os.path.join(args.cam_dir, f"{core_name}.npy")
        gradcam_cam_dict = np.load(gradcam_cam_path, allow_pickle=True).item()


        class_k_idx = None
        for key in ['w1', 'w1-w2', 'w1-w3', 'aggregate']:
            if key in gradcam_cam_dict:
                outputs = gradcam_cam_dict[key]
                class_k_idx = outputs.get('class_k_idx', None)
                if class_k_idx is not None:
                    break

        if class_k_idx is not None and 0 <= class_k_idx < len(class_names_car):
            class_k_label = class_names_car[class_k_idx]
        else:
            class_k_label = 'Unknown'

        normalized_class_k_label = normalize_label(class_k_label)
        second_img_path = None
        if normalized_class_k_label in class_to_image_paths:
            candidate_paths = class_to_image_paths[normalized_class_k_label]
            if len(candidate_paths) > 1:
                second_img_path = next((p for p in candidate_paths if p != img_path), candidate_paths[0])
            elif len(candidate_paths) == 1:
                second_img_path = candidate_paths[0]

        second_image = load_and_preprocess_image(second_img_path)
 

        second_image_resized = cv2.resize(second_image, (224, 224))
        vis_list.append((second_image_resized * 255).astype(np.uint8))
        labels.append(f'{class_k_label}')

        cam_method_name = 'gradcam'
        cam_path = os.path.join(args.cam_dir, f"{core_name}.npy")
        cam_dict = np.load(cam_path, allow_pickle=True).item()


        for key in ['GradCAM', 'Finer_diff_1', 'Finer_diff_2', 'Finer_agg']:
            if key in cam_dict:
                outputs = cam_dict[key]
                cams = outputs.get('highres', None)
                if cams is None:
                    continue
                cam = cams[0].squeeze()
                visualization = visualize_cam_on_image(original_image, cam)
                vis_list.append(visualization)
                labels.append(f"{cam_method_name}_{key}")

        padding_height = 40
        images_with_labels = []
        for img, label in zip(vis_list, labels):
            label_img = np.full((padding_height, img.shape[1], 3), 255, dtype=np.uint8)
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.4
            thickness = 1
            text_size, _ = cv2.getTextSize(label, font, font_scale, thickness)
            text_x = max((img.shape[1] - text_size[0]) // 2, 0)
            text_y = (padding_height + text_size[1]) // 2 - 5
            cv2.putText(label_img, label, (text_x, text_y), font, font_scale, (0, 0, 0), thickness)
            img_with_label = np.vstack((label_img, img))
            images_with_labels.append(img_with_label)

        margin_size = 10
        margin_color = (255, 255, 255)

        target_height = images_with_labels[0].shape[0]
        for i, img in enumerate(images_with_labels):
            if img.shape[0] != target_height:
                images_with_labels[i] = cv2.resize(img, (img.shape[1], target_height))

        concatenated_image = images_with_labels[0]
        for img in images_with_labels[1:]:
            margin = np.full((concatenated_image.shape[0], margin_size, 3), margin_color, dtype=np.uint8)
            concatenated_image = np.hstack((concatenated_image, margin, img))

        output_filename = f"{core_name}_concatenated.jpg"
        output_path = os.path.join(args.save_dir, output_filename)
        cv2.imwrite(output_path, concatenated_image)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Visualization')
    parser.add_argument('--dataset_path', type=str, required=True, help='Path to the dataset directory')
    parser.add_argument('--cams_path', type=str, required=True, help='Path to the CAMs directory')
    parser.add_argument('--save_dir', type=str, required=True, help='Path to save visualizations')
    args = parser.parse_args()
    main(args)