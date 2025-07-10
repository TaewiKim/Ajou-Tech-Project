// 객체 리터럴
const person = {
  name: "Taewi",
  age: 28,
  greet: function() {
    console.log(`Hello, my name is ${this.name}`);
  }
};

person.greet(); // Hello, my name is Taewi

// 속성 추가
person.isStudent = true;
console.log(person.isStudent); // true

// 속성 삭제
delete person.age;
console.log(person.age); // undefined
