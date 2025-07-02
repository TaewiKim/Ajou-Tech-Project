// 배열
const fruits = ["apple", "banana", "orange"];
fruits.push("kiwi");
console.log(fruits);

// 객체
const person = {
  name: "Taewi",
  age: 28,
  greet: function () {
    console.log("Hi, I'm " + this.name);
  }
};

person.greet();
