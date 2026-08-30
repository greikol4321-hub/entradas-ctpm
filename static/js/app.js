// CTPM — invisible details compound (Emil)
// arrancar siempre en el tope: desactivar restauración de scroll (evita bajarse al form al recargar/entrar)
if('scrollRestoration' in history) history.scrollRestoration='manual';
window.scrollTo(0,0);
const navToggle=document.getElementById('navToggle'), mobileNav=document.getElementById('mobileNav'), headerEl=document.querySelector('.header');
if(navToggle && mobileNav){
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
console.log('CTPM — taste is trained');
