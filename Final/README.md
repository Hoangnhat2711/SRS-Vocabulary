# Final · SRS Vocabulary React

Đây là bản **100% ReactJS** của ứng dụng học từ vựng SRS.

Ứng dụng **không cần Python backend** để chạy. Toàn bộ logic học, dữ liệu tiến độ và điều phối lượt học đều chạy ngay trong frontend.

## Cách hoạt động

- dữ liệu từ vựng được lấy từ thư mục `vocab_sets/`
- logic SRS chạy bằng JavaScript trong `src/lib/`
- tiến độ học được lưu trong `localStorage` của trình duyệt

## Cấu trúc chính

- `src/App.jsx`: giao diện chính
- `src/lib/srsCore.js`: lõi thuật toán SRS
- `src/lib/srsStore.js`: lớp dữ liệu frontend + lưu `localStorage`
- `vocab_sets/`: nơi đặt file từ vựng JSON

## Cài đặt

```bash
npm install
```

## Chạy phát triển

```bash
npm run dev
```

Mở tại:

```text
http://127.0.0.1:4173
```

## Build production

```bash
npm run build
```

## Xem bản build local

```bash
npm run preview
```

Hoặc:

```bash
npm run start
```

## Bộ từ vựng

Muốn thêm hoặc thay dữ liệu, hãy copy file JSON vào `vocab_sets/`.

Lưu ý: vì app React hiện bundle dữ liệu lúc chạy dev/build, sau khi thêm file mới bạn nên chạy lại `npm run dev` hoặc `npm run build` để ứng dụng nhận bộ từ mới.

## Lưu tiến độ

Tiến độ học không còn ghi ra Python log file nữa. Ứng dụng lưu trực tiếp trong `localStorage` của trình duyệt.

Nếu muốn reset sạch hoàn toàn, có thể:

- dùng nút reset trong giao diện
- hoặc xóa `localStorage` của trang trong trình duyệt

## Ghi chú

Các file Python cũ trong thư mục chỉ còn là phần dư từ quá trình chuyển đổi, không còn là dependency để bản React hoạt động.
