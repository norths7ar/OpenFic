import "./cover-cropper.css";
/**
 * CoverCropper Component
 *
 * 封面裁剪器组件，支持图片选择、预览和裁剪（固定 2:3 比例）。
 * 裁剪功能使用覆盖式 Dialog 弹窗显示。
 */
import { Box, Button, Dialog, Flex, Text } from "@radix-ui/themes";
import { Upload } from "lucide-react";
import { useState, useCallback, useRef } from "react";
import Cropper, { type Area } from "react-easy-crop";
import { useTranslation } from "react-i18next";

interface CoverCropperProps {
  /** 当前裁剪后的文件 */
  value: File | null;
  /** 文件变更回调 */
  onChange: (file: File | null) => void;
  /** 现有封面预览 URL（编辑模式） */
  previewUrl?: string | null;
}

/** 裁剪区域信息 */
interface CroppedArea {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * 创建裁剪后的图片文件。
 */
async function getCroppedImage(imageSrc: string, croppedAreaPixels: CroppedArea): Promise<File> {
  const image = new Image();
  image.src = imageSrc;

  await new Promise((resolve) => {
    image.onload = resolve;
  });

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;

  // 设置画布尺寸为裁剪区域尺寸
  canvas.width = croppedAreaPixels.width;
  canvas.height = croppedAreaPixels.height;

  // 绘制裁剪后的图片
  ctx.drawImage(
    image,
    croppedAreaPixels.x,
    croppedAreaPixels.y,
    croppedAreaPixels.width,
    croppedAreaPixels.height,
    0,
    0,
    croppedAreaPixels.width,
    croppedAreaPixels.height,
  );

  // 转换为 Blob
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(new File([blob], "cover.jpg", { type: "image/jpeg" }));
      }
    }, "image/jpeg");
  });
}

export function CoverCropper({ value, onChange, previewUrl }: CoverCropperProps) {
  const { t } = useTranslation();
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /** 处理文件选择 */
  const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      setImageSrc(reader.result as string);
      // 重置裁剪状态
      setCrop({ x: 0, y: 0 });
      setZoom(1);
    };
    reader.readAsDataURL(file);
  }, []);

  /** 裁剪完成回调 */
  const onCropComplete = useCallback((_croppedArea: Area, croppedAreaPixels: Area) => {
    setCroppedAreaPixels(croppedAreaPixels);
  }, []);

  /** 确认裁剪 */
  const handleCropConfirm = useCallback(async () => {
    if (!imageSrc || !croppedAreaPixels) return;

    try {
      const croppedFile = await getCroppedImage(imageSrc as string, croppedAreaPixels);
      onChange(croppedFile);
      setImageSrc(null);
    } catch (error) {
      console.error("裁剪失败:", error);
    }
  }, [imageSrc, croppedAreaPixels, onChange]);

  /** 取消裁剪 */
  const handleCropCancel = useCallback(() => {
    setImageSrc(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  // 显示模式（已有封面或预览）
  const displayUrl = value ? URL.createObjectURL(value) : previewUrl;

  return (
    <Box>
      <Text
        as="label"
        size="2"
        weight="medium"
        mb="2"
        className="cover-cropper__label"
      >
        {t("coverCropper.projectCover")}
      </Text>

      {displayUrl ? (
        <Box>
          <Box className="cover-cropper__preview">
            <img
              src={displayUrl}
              alt={t("coverCropper.coverPreview")}
              className="cover-cropper__image"
            />
          </Box>
          <Button
            mt="2"
            variant="soft"
            size="2"
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
          >
            {t("coverCropper.changeCover")}
          </Button>
        </Box>
      ) : (
        <Box
          className="cover-cropper__dropzone"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            fileInputRef.current?.click();
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--accent-a8)";
            e.currentTarget.style.background = "var(--accent-a2)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--gray-a7)";
            e.currentTarget.style.background = "var(--gray-a2)";
          }}
        >
          <Upload
            size={24}
            className="cover-cropper__upload-icon"
          />
          <Text
            size="1"
            color="gray"
          >
            {t("coverCropper.uploadCover")}
          </Text>
        </Box>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="cover-cropper__file-input"
        onChange={handleFileSelect}
      />

      {/* 裁剪弹窗 */}
      <Dialog.Root
        open={!!imageSrc}
        onOpenChange={(open) => {
          if (!open) {
            handleCropCancel();
          }
        }}
      >
        <Dialog.Content maxWidth="600px">
          <Dialog.Title>{t("coverCropper.cropCover")}</Dialog.Title>
          <Dialog.Description
            size="2"
            color="gray"
          >
            {t("coverCropper.cropDescription")}
          </Dialog.Description>

          <Box
            mt="4"
            className="cover-cropper__crop-area"
          >
            {imageSrc && (
              <Cropper
                image={imageSrc}
                crop={crop}
                zoom={zoom}
                aspect={2 / 3}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={onCropComplete}
              />
            )}
          </Box>

          <Flex
            gap="3"
            mt="4"
            justify="end"
          >
            <Button
              variant="soft"
              color="gray"
              type="button"
              onClick={handleCropCancel}
            >
              {t("common.cancel")}
            </Button>
            <Button
              type="button"
              onClick={handleCropConfirm}
            >
              {t("coverCropper.confirmCrop")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
    </Box>
  );
}
