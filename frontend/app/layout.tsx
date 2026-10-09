import type { Metadata } from "next";
import { Be_Vietnam_Pro, Playfair_Display } from "next/font/google";
import { Header } from "@/components/common/Header";
import { Footer } from "@/components/common/Footer";
import { Providers } from "@/components/common/Providers";
import "./globals.css";

// Self-hosted at build time by next/font, so the CSP can keep font-src 'self'.
const beVietnamPro = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-be-vietnam-pro",
  display: "swap",
});

const playfairDisplay = Playfair_Display({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
  variable: "--font-playfair-display",
  display: "swap",
});

export const metadata: Metadata = {
  // Favicon, apple-touch-icon and the share image come from app/icon.svg,
  // app/apple-icon.png and app/opengraph-image.png (RoomBeacon bear mark).
  metadataBase: new URL(process.env.SITE_URL ?? "http://localhost:3000"),
  title: "RoomBeacon — Tìm phòng trọ TP.HCM, biết rõ giá trước khi thuê",
  description:
    "Nền tảng tìm phòng trọ, căn hộ thuê tại TP.HCM dựa trên dữ liệu thật. Biết rõ giá trung vị thị trường từng quận, phường trước khi hỏi thuê.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className={`${beVietnamPro.variable} ${playfairDisplay.variable}`}>
      <body className="min-h-screen bg-bg text-ink font-sans antialiased flex flex-col">
        <Providers>
          <Header />
          <div className="flex-1">{children}</div>
          <Footer />
        </Providers>
      </body>
    </html>
  );
}
