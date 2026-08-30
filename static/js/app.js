// CTPM — invisible details compound (Emil)
// arrancar siempre en el tope: desactivar restauración de scroll (evita bajarse al form al recargar/entrar)
if('scrollRestoration' in history) history.scrollRestoration='manual';
window.scrollTo(0,0);
const navToggle=document.getElementById('navToggle'), mobileNav=document.getElementById('mobileNav'), headerEl=document.querySelector('.header');if(navToggle && mobileNav){
  navToggle.addEventListener('click',()=>{
    const hidden=mobileNav.classList.toggle('hidden');
    navToggle.classList.toggle('is-open', !hidden);
    navToggle.setAttribute('aria-expanded', !hidden);
  });
  mobileNav.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{
    mobileNav.classList.add('hidden');
    navToggle.classList.remove('is-open');
    navToggle.setAttribute('aria-expanded','false');
  }));
}
// headroom — nav se esconde al bajar y vuelve al subir, sin saltos
(function(){
  const h=document.querySelector('.header');
  if(!h) return;
  let lastY=window.scrollY, ticking=false;
  const threshold=8, hideAfter=100;
  window.addEventListener('scroll',()=>{
    if(ticking) return;
    ticking=true;
    requestAnimationFrame(()=>{
      const y=window.scrollY;
      const diff=y-lastY;
      const menuOpen=mobileNav && !mobileNav.classList.contains('hidden');
      if(!menuOpen){
        if(y>hideAfter && diff>threshold) h.classList.add('header--hidden');
        else if(diff<-threshold || y<=hideAfter) h.classList.remove('header--hidden');
      }
      h.classList.toggle('header--scrolled', y>10);
      lastY=y;
      ticking=false;
    });
  },{passive:true});
})();
// Scroll reveals — IntersectionObserver, not scroll listener
const reveals=document.querySelectorAll('.reveal');
if(reveals.length){
  if('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches){
    const io=new IntersectionObserver((entries)=>{
      entries.forEach(e=>{
        if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); }
      });
    },{threshold:0.12, rootMargin:'0px 0px -40px 0px'});
    reveals.forEach(el=>io.observe(el));
    document.querySelectorAll('.hero .reveal, .admin-head.reveal').forEach(el=>el.classList.add('in'));
  } else {
    reveals.forEach(el=>el.classList.add('in'));
  }
}
if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){
  document.documentElement.style.setProperty('--ease-out','linear');
}
// toast futurista — globl, reemplaza alert()/banners. tipos: success|error|info|warning
window.showToast=function(tipo, msg, opts){
  const root=document.getElementById('toast-root');
  if(!root) return;
  const icons={success:'✓',error:'✕',info:'i',warning:'!'};
  const t=document.createElement('div');
  t.className='toast '+tipo;
  t.setAttribute('role', tipo==='error'?'alert':'status');
  t.innerHTML='<div class="toast-glass"><span class="toast-icon">'+icons[tipo||'info']+'</span><span class="toast-msg"></span><span class="toast-progress"></span></div>';
  t.querySelector('.toast-msg').textContent=msg;
  root.appendChild(t);
  const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const dur=opts&&opts.duration?opts.duration:3800;
  let gone=false;
  const dismiss=()=>{
    if(gone) return; gone=true;
    t.classList.add('exiting');
    setTimeout(()=>t.remove(), reduce?0:200);
  };
  setTimeout(dismiss, dur);
  t.addEventListener('click',dismiss);
  // antipicamente: anticipación — contrae antes de salir (solo si no es motion-reduced)
  if(!reduce){ setTimeout(()=>t.classList.add('anticipate'), Math.max(0,dur-120)); }
};
console.log('CTPM — taste is trained');
