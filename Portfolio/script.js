// Smooth scrolling

document.querySelectorAll('a[href^="#"]').forEach(link => {

    link.addEventListener('click', function(e) {

        const target = document.querySelector(
            this.getAttribute('href')
        );

        if (target) {
            e.preventDefault();

            target.scrollIntoView({
                behavior: 'smooth'
            });
        }

    });

});


// Terminal typing effect

const status = document.querySelector(".status");

const messages = [
    "● Learning & Building",
    "● Exploring Cybersecurity",
    "● Developing Skills",
    "● Practicing Networking"
];

let index = 0;

setInterval(() => {

    index = (index + 1) % messages.length;

    status.textContent = messages[index];

}, 2500);