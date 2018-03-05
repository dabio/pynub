;(function() {

  const
    cookieName = "deleteMe",
    cookieDays = 14,
    dimClassName = 'dim';

  var
    dimElement = function(el) {
      el.classList.add(dimClassName)
    },

    undimElement = function(el) {
      el.classList.remove(dimClassName)
    },

    showElement = function(el) {
      el.style.display = 'inline'
    },

    hideElement = function(el) {
      el.style.display = 'none'
    },

    findCookie = function(name) {
      var cookies = document.cookie.split(';')
      for (var i = cookies.length - 1; i >= 0; i--) {
        if (cookies[i].indexOf(cookieName+'=') != -1) {
          return cookies[i]
        }
      }
    },

    cookieList = function() {
      var list = [],
        c = findCookie(cookieName) || cookieName+'=';

      c = c.trim().replace(cookieName+'=', '')
      if (c.length != 0) {
        list = c.split(',')
      }

      return list
    },

    updateCookieList = function(list) {
      var date = new Date();

      if (list.length > 0) {
        date.setTime(date.getTime()+(cookieDays*24*60*60*1000))
      }
      document.cookie = cookieName+'='+list+'; expires='+date.toGMTString();
    },

    deleteClicked = function(el) {
      dimElement(el.parentElement.parentElement)
      showElement(el.nextElementSibling)

      var list = cookieList()
      list.push(el.dataset.id)
      list = list.filter(function(v, k, self) {
        return self.indexOf(v) == k
      })

      updateCookieList(list)
    },

    cancelClicked = function(el) {
      undimElement(el.parentElement.parentElement)
      hideElement(el)

      var list = cookieList()
      list.splice(list.indexOf(el.dataset.id), 1)

      updateCookieList(list)
    }
  ;

  document.querySelectorAll('a.delete').forEach((el, index) => {
    el.addEventListener('click', function() {deleteClicked(el)})
  });
  document.querySelectorAll('a.cancel').forEach((el, index) => {
    el.addEventListener('click', function() {cancelClicked(el)})
  });

  // This removes all "deleteMe" cookie information. When this code gets
  // called, the cookie was send to the server and (hopefully) removed
  // already.
  document.cookie = cookieName+'=; Max-Age=-1'

}).call(this)
