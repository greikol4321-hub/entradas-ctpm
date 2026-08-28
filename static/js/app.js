// CTPM — invisible details compound (Emil)
const navToggle=document.getElementById('navToggle'), mobileNav=document.getElementById('mobileNav');
if(navToggle){
  navToggle.addEventListener('click',()=>{
    const hidden=mobileNav.classList.toggle('hidden');
    navToggle.setAttribute('aria-expanded', !hidden);
    navToggle.children[0].style.transform=hidden?'':'translateY(3.5px) rotate(45deg)';
    navToggle.children[1].style.transform=hidden?'':'translateY(-3.5px) rotate(-45deg)';
  });
}
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
