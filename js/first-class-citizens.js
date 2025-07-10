// 함수를 변수에 할당
const sayHello = function() {
  console.log("Hello!");
};
sayHello(); // Hello!

// 함수를 다른 함수의 인자로 전달
function executeTwice(fn) {
  fn();
  fn();
}
executeTwice(sayHello); 
// Hello!
// Hello!

// 함수를 리턴
function multiplier(factor) {
  return function(number) {
    return number * factor;
  }
}

const double = multiplier(2);
console.log(double(5)); // 10
