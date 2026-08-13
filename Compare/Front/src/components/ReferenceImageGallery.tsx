import { useMemo } from "react";
import type { PublicReferenceCategory, PublicReferenceImage } from "../contracts/workbench";
import { Icon } from "./icons";
import { Button } from "./ui";

const categoryLabels: Record<PublicReferenceCategory, string> = {
  equipment: "融资设备",
  "raw-material": "原材料",
  process: "工艺",
  "finished-product": "成品",
};

export function ReferenceImageGallery({ images, selectedImageId, onSelect, onClose }: {
  images: PublicReferenceImage[];
  selectedImageId: string;
  onSelect: (imageId: string) => void;
  onClose: () => void;
}) {
  const selected = images.find((image) => image.id === selectedImageId) ?? images[0];
  const groups = useMemo(() => {
    const grouped = new Map<PublicReferenceCategory, PublicReferenceImage[]>();
    images.forEach((image) => grouped.set(image.category, [...(grouped.get(image.category) ?? []), image]));
    return [...grouped.entries()];
  }, [images]);
  if (!selected) return null;
  const selectedGroup = images.filter((image) => image.category === selected.category);
  const index = selectedGroup.findIndex((image) => image.id === selected.id);
  const selectOffset = (offset: number) => onSelect(selectedGroup[(index + offset + selectedGroup.length) % selectedGroup.length].id);
  return (
    <div className="reference-image-gallery" data-selected-reference-image-id={selected.id}>
      <header>
        <div><Icon name="image" /><span><strong>公开参考图集</strong><small>本地静态资产 · 来源和许可逐张记录</small></span></div>
        <Button onClick={onClose}>返回原始材料</Button>
      </header>
      <p className="public-reference-warning"><strong>公开参考图 / 非本项目客户现场 / 不参与风险事实认定</strong><span>仅辅助理解设备类别和“原材料—工艺—成品”视觉语义，不作为客户材料或 FactVersion。</span></p>
      <nav className="reference-gallery-groups" aria-label="参考图片分组">
        {groups.map(([category, group]) => <button aria-pressed={selected.category === category} className={selected.category === category ? "is-active" : ""} key={category} onClick={() => onSelect(group[0].id)} type="button"><strong>{categoryLabels[category]}</strong><small>{group.length} 张</small></button>)}
      </nav>
      <figure className="reference-gallery-main">
        <img alt={`${selected.title}，公开参考图，非本项目客户现场`} src={selected.src} />
        <div className="reference-gallery-controls"><Button aria-label="上一张参考图" onClick={() => selectOffset(-1)}>←</Button><span>{index + 1} / {selectedGroup.length}</span><Button aria-label="下一张参考图" onClick={() => selectOffset(1)}>→</Button></div>
        <figcaption><strong>{selected.title}</strong><span>{selected.description}</span></figcaption>
      </figure>
      <div className="reference-gallery-thumbnails" aria-label={`${categoryLabels[selected.category]}缩略图条`}>
        {selectedGroup.map((image) => <button aria-pressed={image.id === selected.id} className={image.id === selected.id ? "is-active" : ""} key={image.id} onClick={() => onSelect(image.id)} type="button"><img alt="" src={image.src} /><span>{image.title}</span></button>)}
      </div>
      <dl className="reference-gallery-meta">
        <div><dt>来源</dt><dd>{selected.author}</dd></div>
        <div><dt>分组 / 阶段</dt><dd>{categoryLabels[selected.category]}</dd></div>
        <div><dt>许可</dt><dd><a href={selected.licenseUrl} rel="noreferrer" target="_blank">{selected.license}</a></dd></div>
        <div><dt>原始页面</dt><dd><a href={selected.originUrl} rel="noreferrer" target="_blank">查看来源记录</a></dd></div>
        <div><dt>用途</dt><dd>{selected.usage}</dd></div>
      </dl>
    </div>
  );
}
