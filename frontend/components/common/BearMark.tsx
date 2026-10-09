import React from "react";

interface BearMarkProps {
  className?: string;
  title?: string;
}

/** RoomBeacon mark: a mini bear peeking out of a teal house with a beacon light (brand/logo-mark.svg). */
export const BearMark: React.FC<BearMarkProps> = ({ className = "", title }) => (
  <svg
    viewBox="0 0 128 128"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    role={title ? "img" : undefined}
    aria-hidden={title ? undefined : true}
    focusable="false"
  >
    {title ? <title>{title}</title> : null}
    <path d="M64 8 L120 52 V112 a8 8 0 0 1 -8 8 H16 a8 8 0 0 1 -8 -8 V52 Z" fill="#0F5F58" />
    <path
      d="M64 8 L120 52 V112 a8 8 0 0 1 -8 8 H16 a8 8 0 0 1 -8 -8 V52 Z"
      fill="none"
      stroke="#B8892E"
      strokeWidth="3"
      strokeLinejoin="round"
    />
    <circle cx="64" cy="36" r="6" fill="#E9C46A" />
    <circle cx="40" cy="62" r="11" fill="#C8956A" />
    <circle cx="88" cy="62" r="11" fill="#C8956A" />
    <circle cx="40" cy="62" r="5.5" fill="#F2D3B3" />
    <circle cx="88" cy="62" r="5.5" fill="#F2D3B3" />
    <path d="M28 120 V92 a36 34 0 0 1 72 0 V120 Z" fill="#C8956A" />
    <ellipse cx="64" cy="104" rx="14" ry="10" fill="#F7E6D3" />
    <ellipse cx="64" cy="99" rx="5" ry="3.8" fill="#3B2A20" />
    <path d="M59 105.5 Q64 110 69 105.5" fill="none" stroke="#3B2A20" strokeWidth="2.2" strokeLinecap="round" />
    <circle cx="52" cy="88" r="3.8" fill="#1F1A17" />
    <circle cx="76" cy="88" r="3.8" fill="#1F1A17" />
    <circle cx="53.2" cy="86.7" r="1.2" fill="#FFFFFF" />
    <circle cx="77.2" cy="86.7" r="1.2" fill="#FFFFFF" />
    <ellipse cx="44" cy="99" rx="5" ry="3" fill="#F29B93" opacity="0.6" />
    <ellipse cx="84" cy="99" rx="5" ry="3" fill="#F29B93" opacity="0.6" />
  </svg>
);
