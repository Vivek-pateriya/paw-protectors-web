// Copyright (c) 2026 Vivek Pateriya.
import React, { useEffect, useRef } from 'react';
import creatorPhoto from './assets/vivek-pateriya.jpg';

export const copyright = `© ${new Date().getFullYear()} Vivek Pateriya`;

export function ProjectFooter({ onAbout }) {
  return <footer className="project-footer">
    <button type="button" className="about-link" onClick={onAbout}>About the creator & project</button>
    <small>{copyright}</small>
  </footer>;
}

export function About({ onClose }) {
  const dialog = useRef(null);
  useEffect(() => { dialog.current.showModal(); }, []);
  return <dialog ref={dialog} className="about-dialog" aria-labelledby="about-title" onCancel={onClose} onClose={onClose}>
    <div className="dialog-head">
      <h2 id="about-title">About Paw Protectors</h2>
      <button type="button" className="close" aria-label="Close about" onClick={onClose}>×</button>
    </div>
    <section aria-labelledby="creator-title">
      <img className="creator-photo" src={creatorPhoto} alt="Vivek Pateriya, creator of Paw Protectors" />
      <p className="eyebrow">MEET THE CREATOR</p>
      <h3 id="creator-title">Vivek Pateriya</h3>
      <p>Creator of Paw Protectors. I built this project to bring pet care, adoption and pet essentials together in one place.</p>
      <a className="about-link" href="https://www.linkedin.com/in/vivek-pateriya-73090a1a7/" target="_blank" rel="noopener noreferrer">Connect with Vivek on LinkedIn ↗</a>
    </section>
    <section aria-labelledby="project-title">
      <h3 id="project-title">About the project</h3>
      <p>Paw Protectors helps pet owners, veterinarians and administrators stay connected through pet profiles, health records, appointments and care reminders.</p>
      <p>Owners can submit animals for adoption with admin approval. The Pet Shop brings together pet essentials, a shared cart and cash-on-delivery orders.</p>
      <p>The React JS website and React Native app share a FastAPI backend and PostgreSQL database, keeping the same account and records available on both.</p>
    </section>
    <p className="about-copyright">{copyright} · Paw Protectors</p>
  </dialog>;
}
