// Desktop browsers ignore <input capture> and open the file dialog, so "카메라로
// 찍기" there is a live preview (getUserMedia) with a shutter instead.
import { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';

import { Button, T } from '@/components/ui';

export function WebCamera({
  onCapture,
  onProblem,
  onClose,
}: {
  onCapture: (f: File) => void;
  onProblem: (kind: 'denied' | 'no_camera') => void;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    dialog.current?.focus(); // keyboard and screen reader users land in the dialog
    let gone = false;
    navigator.mediaDevices
      .getUserMedia({
        // the back camera where there is one; as sharp as it gives, for OCR
        video: { facingMode: 'environment', width: { ideal: 3840 }, height: { ideal: 2160 } },
        audio: false,
      })
      .then((s) => {
        if (gone) return s.getTracks().forEach((t) => t.stop());
        stream.current = s;
        if (video.current) video.current.srcObject = s;
      })
      .catch((e: DOMException) => {
        if (gone) return;
        onProblem(e.name === 'NotAllowedError' || e.name === 'SecurityError' ? 'denied' : 'no_camera');
      });
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', esc);
    return () => {
      gone = true;
      window.removeEventListener('keydown', esc);
      stream.current?.getTracks().forEach((t) => t.stop());
    };
  }, [onClose, onProblem]);

  const shoot = () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext('2d')!.drawImage(v, 0, 0);
    canvas.toBlob(
      (b) => b && onCapture(new File([b], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' })),
      'image/jpeg',
      0.92,
    );
  };

  return (
    <div
      ref={dialog}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-label="카메라로 찍기"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: '#000',
        display: 'flex',
        flexDirection: 'column',
        outline: 'none',
      }}
    >
      <video
        ref={video}
        autoPlay
        playsInline
        muted
        onLoadedMetadata={() => setReady(true)}
        style={{ flex: 1, minHeight: 0, width: '100%', objectFit: 'contain' }}
      />
      <View style={{ padding: 16, gap: 12, alignItems: 'center' }}>
        <T style={{ color: '#FFFFFF', textAlign: 'center' }}>
          {ready ? '문제가 화면에 꽉 차게 맞춘 뒤 찍어 주세요' : '카메라를 켜고 있어요…'}
        </T>
        <View style={{ flexDirection: 'row', gap: 12, width: '100%', maxWidth: 480 }}>
          <Button kind="secondary" label="취소" onPress={onClose} style={{ flex: 1 }} />
          <Button
            kind={ready ? 'large' : 'waiting'}
            icon="camera"
            label="찍기"
            onPress={shoot}
            style={{ flex: 2 }}
          />
        </View>
      </View>
    </div>
  );
}
